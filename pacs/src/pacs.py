import glob
import kapteyn
import numpy
import os
import pyfits
import re
import tempfile

from matplotlib import pyplot
from mpi4py import MPI
from tamasis import numpyutils
from tamasis.core import *
from tamasis.config import __verbose__, __version__
from tamasis.observations import Observation, Instrument, FlatField, create_scan

__all__ = [ 'PacsObservation', 'PacsSimulation', 'pacs_create_scan', 'pacs_plot_scan', 'pacs_preprocess' ]

DEFAULT_RESOLUTION = {'blue':3.2, 'green':3.2, 'red':6.4}

PACS_POINTING_DTYPE = [('time', get_default_dtype_float()), ('ra', get_default_dtype_float()),
                       ('dec', get_default_dtype_float()), ('pa', get_default_dtype_float()),
                       ('chop', get_default_dtype_float()), ('info', numpy.int64), ('masked', numpy.bool8),
                       ('removed', numpy.bool8)]

PACS_ACCELERATION = 4.
PACS_SAMPLING = 0.024996

class _Pacs(Observation):

    def get_pointing_matrix(self, header, resolution, npixels_per_sample=0, method=None, oversampling=True):
        if method is None:
            method = 'sharp'
        method = method.lower()
        if method not in ('nearest', 'sharp'):
            raise ValueError("Invalid method '" + method + "'. Valids methods are 'nearest' or 'sharp'")

        nsamples = self.get_nfinesamples() if oversampling else self.get_nsamples()
        if header is None:
            if MPI.COMM_WORLD.Get_size() > 1:
                raise ValueError('With MPI, the map header must be specified.')
            header = self.get_map_header(resolution, oversampling)
        elif isinstance(header, str):
            header = _str2fitsheader(header)

        ndetectors = self.get_ndetectors()
        nvalids = int(numpy.sum(nsamples))
        if npixels_per_sample != 0:
            sizeofpmatrix = npixels_per_sample * nvalids * ndetectors
            print('Info: Allocating '+str(sizeofpmatrix/2.**17)+' MiB for the pointing matrix.')
        else:
            sizeofpmatrix = 1
        pmatrix = numpy.empty(sizeofpmatrix, dtype=numpy.int64)
        
        new_npixels_per_sample, status = \
            tmf.pacs_pointing_matrix(self.instrument.band,
                                     nvalids,
                                     numpy.ascontiguousarray(self.slice.nsamples_all, dtype='int32'),
                                     numpy.ascontiguousarray(self.slice.compression_factor, dtype='int32'),
                                     self.instrument.fine_sampling_factor,
                                     oversampling,
                                     numpy.ascontiguousarray(self.pointing.time),
                                     numpy.ascontiguousarray(self.pointing.ra),
                                     numpy.ascontiguousarray(self.pointing.dec),
                                     numpy.ascontiguousarray(self.pointing.pa),
                                     numpy.ascontiguousarray(self.pointing.chop),
                                     numpy.ascontiguousarray(self.pointing.masked, dtype='int8'),
                                     numpy.ascontiguousarray(self.pointing.removed,dtype='int8'),
                                     method,
                                     numpy.asfortranarray(self.instrument.detector_mask, dtype='int8'),
                                     self.get_ndetectors(),
                                     self.instrument.detector_center.base.base.swapaxes(0,1).copy().T,
                                     self.instrument.detector_corner.base.base.swapaxes(0,1).copy().T,
                                     numpy.asfortranarray(self.instrument.detector_area),
                                     self.instrument.distortion_yz.base.base.T,
                                     npixels_per_sample,
                                     str(header).replace('\n',''),
                                     pmatrix)
        if status != 0: raise RuntimeError()

        # the number of pixels per sample is now known, do the real computation
        if npixels_per_sample == 0:
            return self.get_pointing_matrix(header, resolution, new_npixels_per_sample, method, oversampling)

        return pmatrix, header, ndetectors, nsamples, npixels_per_sample, ('/detector', '/pixel')

    def get_filter_uncorrelated(self):
        """
        Read an inverse noise time-time correlation matrix from a calibration file, in PACS-DP format.
        """
        ncorrelations, status = tmf.pacs_read_filter_calibration_ncorrelations(self.instrument.band)
        if status != 0: raise RuntimeError()

        data, status = tmf.pacs_read_filter_calibration(self.instrument.band, ncorrelations, self.get_ndetectors(), numpy.asfortranarray(self.instrument.detector_mask, numpy.int8))
        if status != 0: raise RuntimeError()

        return data.T

    @property
    def status(self):
        if self._status is not None:
            return self._status
        
        status = []
        for filename in self.slice.filename:
            hdu = pyfits.open(filename)['STATUS']
            while True:
                try:
                    s = hdu.data
                    break
                except IndexError as errmsg:
                    pass
            
            status.append(s.base)

        # check number of records
        if numpy.any([len(s) for s in status] != self.slice.nsamples_all):
            raise ValueError("The status has a number of records '" + str([len(s) for s in status]) + "' incompatible with that of the pointings '" + str(self.slice.nsamples_all) + "'.")

        # merge status if necessary
        if any([status[i].dtype != status[0].dtype for i in range(1,len(status))]):
            newdtype = []
            for d in status[0].dtype.names:
                newdtype.append((d, max(status, key=lambda s: s[d].dtype.itemsize)[d].dtype))
            self._status = numpy.recarray(int(numpy.sum(self.slice.nsamples_all)), newdtype)
            dest = 0
            for s in status:
                for n in status[0].dtype.names:
                    self._status[n][dest:dest+len(s)] = s[n]
                dest += len(s)
        else:
            self._status = numpy.concatenate(status).view(numpy.recarray)
        return self._status

    def __str__(self):

        # some helpers
        def same(a):
            return all(a == a[0])
        def plural(s,n,prepend=True,s2=''):
            if n == 0:
                return 'no ' + s
            elif n == 1:
                return ('1 ' if prepend else '') + s + s2
            else:
                return (str(n) + ' ' if prepend else '') + s + 's' + s2
        def ad_masks(slice, islice):
            if 'nmasks' not in slice.dtype.names:
                a = []
                d = []
            else:
                a = [m for i, m in enumerate(slice[islice].mask_name)          \
                     if m != '' and slice[islice].mask_activated[i]]
                d = [m for i, m in enumerate(slice[islice].mask_name)          \
                     if m != '' and not slice[islice].mask_activated[i]]
            return (plural('activated mask',   len(a), 0, ': ').capitalize() + \
                        ', '.join(a), 
                    plural('deactivated mask', len(d), 0, ': ').capitalize() + \
                        ', '.join(d))

        nthreads = tmf.info_nthreads()
        ndetectors = self.get_ndetectors()
        sp = len('Info: ')*' '
        unit = 'unknown' if self.slice[0].unit == '' else self.slice[0].unit
        if MPI.COMM_WORLD.Get_size() > 1:
            mpistr = 'Process '+str(MPI.COMM_WORLD.Get_rank()+1) + '/' +       \
                     str(MPI.COMM_WORLD.Get_size()) + ' on node ' +            \
                     MPI.Get_processor_name() + ', '
        else:
            mpistr = ''

        # print general informations
        result = '\nInfo: ' + mpistr + plural('core', nthreads) + ' handling '+ plural('detector', ndetectors) + '\n'
        result += sp + self.instrument.band.capitalize() + ' band, unit is ' + unit + '\n'

        # check if the masks are the same for all the slices
        homogeneous = 'nmasks' not in self.slice.dtype.names or \
                      same(self.slice.nmasks) and all([same(a) for a in self.slice.mask_name.T])
        if homogeneous:
            (a,d) = ad_masks(self.slice, 0)
            result += sp + a + '\n'
            result += sp + d + '\n'
        else:
            result += sp + 'The masks of the observations are heterogeneous\n'

        # print slice-specific information
        dest = 0
        for islice, slice in enumerate(self.slice):

            p = self.pointing[dest:dest+slice.nsamples_all]

            def _str_policy(array):
                if array.size != p.size:
                    raise ValueError('Size problem.')
                
                nkept    = numpy.sum(numpy.logical_and(array, numpy.logical_and(~p.masked, ~p.removed)))
                nmasked  = numpy.sum(numpy.logical_and(array, numpy.logical_and(p.masked, ~p.removed)))
                nremoved = numpy.sum(numpy.logical_and(array, p.removed))

                if nkept+nmasked+nremoved != numpy.sum(array):
                    raise ValueError('This case should not happen.')
                if nkept+nmasked+nremoved == 0:
                    return 'None'
                result = []
                if nkept != 0:
                    result.append(str(nkept)+ ' kept')
                if nmasked != 0:
                    result.append(str(nmasked)+ ' masked')
                if nremoved != 0:
                    result.append(str(nremoved)+ ' removed')
                return ', '.join(result)

            result += sp + 'Observation'
            if self.slice.size > 1:
                result += ' #' + str(islice+1)
            result += ' ' + slice.filename
            first = numpy.argmin(p.removed) + 1
            last = p.size - numpy.argmin(p.removed[::-1])
            result += '[' + str(first) + ':' + str(last) + ']:\n'

            if not homogeneous:
                (a,d) = ad_masks(self.slice, islice)
                result += sp + '      ' + a + '\n'
                result += sp + '      ' + d + '\n'

            result += sp + '      Compression: x' + str(slice.compression_factor) + '\n'
            result += sp + '      In-scan:     ' + _str_policy(p.info == Pointing.INSCAN) + '\n'
            result += sp + '      Turnaround:  ' + _str_policy(p.info == Pointing.TURNAROUND) + '\n'
            result += sp + '      Other:       ' + _str_policy(p.info == Pointing.OTHER)
            if islice + 1 < self.slice.size:
                result += '\n'

        return result

    def _get_detector_mask(self, band, detector_mask, transparent_mode, reject_bad_line):
        shape = (16,32) if band == 'red' else (32,64)
        if type(detector_mask) is str:
            if detector_mask == 'calibration':
                detector_mask, status = tmf.pacs_info_detector_mask(band, shape[0], shape[1])
                if status != 0: raise RuntimeError()
                detector_mask = numpy.ascontiguousarray(detector_mask, numpy.bool8)
            else:
                raise ValueError('Invalid specification for the detector_mask.')
        elif detector_mask is None:
            detector_mask = numpy.zeros(shape, numpy.bool8)
        else:
            if detector_mask.shape != shape:
                raise ValueError('Invalid shape of the input detector mask: ' + str(detector_mask.shape) + ' for the ' + band + ' band.')
            detector_mask = numpy.array(detector_mask, numpy.bool8, copy=False)

        # mask non-transmitting detectors in transparent mode
        if transparent_mode:
            if band == 'red':
                detector_mask[0:8,0:8] = 1
                detector_mask[0:8,16:] = 1
                detector_mask[8:,:]    = 1
            else:
                detector_mask[0:16,0:16] = 1
                detector_mask[0:16,32:]  = 1
                detector_mask[16:,:]     = 1

        # mask erratic line
        if reject_bad_line and band != 'red':
            detector_mask[11,16:32] = 1

        return detector_mask


#-------------------------------------------------------------------------------


class PacsObservation(_Pacs):
    """
    Class which encapsulates handy information about the PACS instrument and 
    the observations to be processed.
    """
    def __init__(self, filename, fine_sampling_factor=1, detector_mask='calibration', reject_bad_line=False, policy_inscan='keep', policy_turnaround='keep', policy_other='remove', policy_invalid='mask'):
        """
        Parameters
        ----------
        filename: string or array of string
              This argument indicates the filenames of the observations
              to be processed. The files must be FITS files, as saved by
              the HCSS method FitsArchive.
        fine_sampling_factor: integer
              Set this value to a power of two, which will increase the
              acquisition model's sampling frequency beyond 40Hz
        detector_mask: None, 'calibration' or boolean array
              If None, no detector will be filtered out. if 'calibration',
              the detector mask will be read from a calibration file.
              Otherwise, it must be of the same shape as the camera:
              (16,32) for the red band and (32,64) for the others.
              Use 0 to keep a detector and 1 to filter it out.
        reject_bad_line: boolean
              If True, the erratic line [11,16:32] (starting from 0) in
              the blue channel will be filtered out
        policy_inscan: 'keep', 'mask' or 'remove'
              This sets the policy for the in-scan frames
        policy_turnaround: 'keep', 'mask' or 'remove'
              This sets the policy for the turnaround frames
        policy_other: 'keep', 'mask' or 'remove'
              This sets the policy for the other frames
        policy_invalid: 'keep', 'mask' or 'remove'
              This sets the policy for the invalid frames

        Returns
        -------
        The returned object contains the following attributes:
        - instrument: information about the instrument
        - pointing: information about the pointings, as a recarray.
        Pointings for which the policy is 'remove' are still available.
        - slice: information about the observations as a recarray
        - status: the HCSS Frames' Status ArrayDataset, as a recarray
        Like the pointing attribute, it also contains the pointings
        for which the policy is 'remove'
        - policy: frame policy

        """
        if type(filename) == str:
            filename = (filename,)
        filename_, nfilenames = _files2tmf(filename)

        band, transparent_mode, nsamples_all, status = tmf.pacs_info_init(filename_, nfilenames)
        if status != 0: raise RuntimeError()
        band = band.strip()

        # get the detector mask, before distributing the detectors to the processors
        detector_mask = self._get_detector_mask(band, detector_mask, transparent_mode, reject_bad_line)

        # get the observations and detector mask for the current processor
        slice_observation, slice_detector = _split_observation(nfilenames, int(numpy.sum(detector_mask == 0)))
        filename = filename[slice_observation]
        nsamples_all = nsamples_all[slice_observation]
        nfilenames = len(filename)
        igood = numpy.where(detector_mask.flat == 0)[0]
        detector_mask = numpy.ones(detector_mask.shape, numpy.bool8)
        detector_mask.flat[igood[slice_detector]] = 0
        filename_, nfilenames = _files2tmf(filename)
        ftype = get_default_dtype_float()

        # frame policy
        policy = MaskPolicy('inscan,turnaround,other,invalid', (policy_inscan, policy_turnaround, policy_other, policy_invalid), 'Frame Policy')

        # store observation information
        mode, compression_factor, unit, ra, dec, cam_angle, scan_angle, scan_length, scan_speed, scan_step, scan_nlegs, frame_time, frame_ra, frame_dec, frame_pa, frame_chop, frame_info, frame_masked, frame_removed, nmasks, mask_name_flat, mask_activated, status = tmf.pacs_info_observation(filename_, nfilenames, numpy.array(policy, dtype='int32'), numpy.sum(nsamples_all))
        if status != 0: raise RuntimeError()

        flen_value = len(unit) // nfilenames
        mode = [mode[i*flen_value:(i+1)*flen_value].strip() for i in range(nfilenames)]
        unit = [unit[i*flen_value:(i+1)*flen_value].strip() for i in range(nfilenames)]

        # store instrument information
        detector_center, detector_corner, detector_area, distortion_yz, oflat, dflat, responsivity, active_fraction, status = \
            tmf.pacs_info_instrument(band, numpy.asfortranarray(detector_mask, numpy.int8))
        if status != 0: raise RuntimeError()

        self.instrument = Instrument('PACS/' + band.capitalize(), detector_mask)
        self.instrument.active_fraction = active_fraction
        self.instrument.band = band
        self.instrument.reject_bad_line = reject_bad_line
        self.instrument.fine_sampling_factor = fine_sampling_factor
        self.instrument.detector_center = detector_center.T.swapaxes(0,1).copy().view(dtype=[('u',ftype),('v',ftype)]).view(numpy.recarray)
        self.instrument.detector_corner = detector_corner.T.swapaxes(0,1).copy().view(dtype=[('u',ftype),('v',ftype)]).view(numpy.recarray)
        self.instrument.detector_area = Map(numpy.ascontiguousarray(detector_area), unit='arcsec^2', origin='upper')
        self.instrument.distortion_yz = distortion_yz.T.view(dtype=[('y',ftype), ('z',ftype)]).view(numpy.recarray)
        self.instrument.flatfield = FlatField(oflat, dflat)
        self.instrument.responsivity = Quantity(responsivity, 'V/Jy')

        # store slice information
        nmasks_max = numpy.max(nmasks)
        if nmasks_max > 0:
            mask_len_max = numpy.max([len(mask_name_flat[(i*32+j)*70:(i*32+j+1)*70].strip()) for j in range(nmasks[i]) for i in range(nfilenames)])
        else:
            mask_len_max = 1

        mask_name      = numpy.ndarray((nfilenames, nmasks_max), 'S'+str(mask_len_max))
        mask_activated = mask_activated.T
        for ifile in range(nfilenames):
            for imask in range(nmasks[ifile]):
                dest = (ifile*32+imask)*70
                mask_name[ifile,imask] = mask_name_flat[dest:dest+mask_len_max].lower()
            isort = numpy.argsort(mask_name[ifile,0:nmasks[ifile]])
            mask_name     [ifile,0:nmasks[ifile]] = mask_name     [ifile,isort]
            mask_activated[ifile,0:nmasks[ifile]] = mask_activated[ifile,isort]

        self.slice = numpy.recarray(nfilenames, dtype=[('filename', 'S256'), ('nsamples_all', int), ('mode', 'S32'), ('compression_factor', int), ('unit', 'S32'), ('ra', float), ('dec', float), ('cam_angle', float), ('scan_angle', float), ('scan_length', float), ('scan_nlegs', int), ('scan_step', float), ('scan_speed', float), ('nmasks', int), ('mask_name', 'S'+str(mask_len_max), nmasks_max), ('mask_activated', bool, nmasks_max)])

        regex = re.compile(r'(.*?)(\[[0-9]*:?[0-9]*\])? *$')
        for ifile, file in enumerate(filename):
            match = regex.match(file)
            self.slice[ifile].filename = match.group(1)

        self.slice.nsamples_all = nsamples_all
        self.slice.nfinesamples = nsamples_all * compression_factor * fine_sampling_factor
        self.slice.mode = mode
        self.slice.compression_factor = compression_factor
        self.slice.unit = unit
        self.slice.ra = ra
        self.slice.dec = dec
        self.slice.cam_angle = cam_angle
        self.slice.scan_angle = scan_angle
        self.slice.scan_length = scan_length
        self.slice.scan_nlegs = scan_nlegs
        self.slice.scan_step = scan_step
        self.slice.scan_speed = scan_speed
        self.slice.nmasks = nmasks
        self.slice.mask_name      = mask_name
        self.slice.mask_activated = mask_activated[:,0:nmasks_max]
        
        # store pointing information
        self.pointing = Pointing(frame_time, frame_ra, frame_dec, frame_pa, frame_info, frame_masked, frame_removed, nsamples=self.slice.nsamples_all, dtype=PACS_POINTING_DTYPE)
        self.pointing.chop = frame_chop

        # Store frame policy
        self.policy = policy

        # Status
        self._status = None

        print(self)

    def get_tod(self, unit='Jy/detector', flatfielding=True, subtraction_mean=True, raw_data=False, masks='activated'):
        """
        Returns the signal and mask timelines.

        By default, if no active mask is specified, the Master mask will
        be retrieved if it exists. Otherwise, the activated masks will
        be read and combined.
        """

        if raw_data:
            flatfielding = False
            subtraction_mean = False

        act_masks = set([m for slice in self.slice for i, m in enumerate(slice.mask_name) \
                         if m not in ('','master') and slice.mask_activated[i]])
        dea_masks = set([m for slice in self.slice for i, m in enumerate(slice.mask_name) \
                         if m not in ('','master') and not slice.mask_activated[i]])
        all_masks = set([m for slice in self.slice for m in slice.mask_name if m != ''])

        if isinstance(masks, str):
            masks = masks.split(',')

        sel_masks = set()
        for m in masks:
            m = m.strip().lower()
            if m == 'all':
                sel_masks |= all_masks
            elif m == 'activated':
                sel_masks |= act_masks
            elif m == 'deactivated':
                sel_masks |= dea_masks
            elif m not in all_masks:
                print("Warning: mask '" + m + "' is not found.")
            else:
                sel_masks.add(m)

        # use 'master' if all activated masks are selected
        if all(['master' in slice.mask_name for slice in self.slice]) and act_masks <= sel_masks:
            sel_masks -= act_masks
            sel_masks.add('master')

        sel_masks = ','.join(sorted(sel_masks))

        signal, mask, status = tmf.pacs_tod(self.instrument.band,
                                            _files2tmf(self.slice.filename)[0],
                                            numpy.asarray(self.slice.nsamples_all, dtype='int32'),
                                            numpy.asarray(self.slice.compression_factor, dtype='int32'),
                                            self.instrument.fine_sampling_factor,
                                            numpy.ascontiguousarray(self.pointing.time),
                                            numpy.ascontiguousarray(self.pointing.ra),
                                            numpy.ascontiguousarray(self.pointing.dec),
                                            numpy.ascontiguousarray(self.pointing.pa),
                                            numpy.ascontiguousarray(self.pointing.chop),
                                            numpy.ascontiguousarray(self.pointing.masked, numpy.int8),
                                            numpy.ascontiguousarray(self.pointing.removed,numpy.int8),
                                            numpy.asfortranarray(self.instrument.detector_mask, numpy.int8),
                                            numpy.asfortranarray(self.instrument.flatfield.detector),
                                            flatfielding,
                                            subtraction_mean,
                                            int(numpy.sum(self.get_nsamples())),
                                            self.get_ndetectors(),
                                            sel_masks)
        if status != 0: raise RuntimeError()
       
        detector = Quantity(self.instrument.detector_area[~self.instrument.detector_mask], 'arcsec^2')
        derived_units = {
            'detector_reference': Quantity(1./self.instrument.active_fraction, 'detector', {'detector':detector}),
            'detector'        : detector,
            'V'               : Quantity(1./self.instrument.responsivity, 'Jy')
            }
        tod = Tod(signal.T, 
                  mask.T,
                  nsamples=self.get_nsamples(),
                  unit=self.slice[0].unit,
                  derived_units=derived_units,
                  copy=False)

        tod.unit = unit
        return tod

    def get_map_header(self, resolution=None, oversampling=True):
        if MPI.COMM_WORLD.Get_size() > 1:
            raise NotImplementedError('The common map header should be specified if more than one job is running.')
        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.instrument.band]

        header, status = tmf.pacs_map_header(self.instrument.band,
                                             numpy.ascontiguousarray(self.slice.nsamples_all, dtype='int32'),
                                             numpy.ascontiguousarray(self.slice.compression_factor, dtype='int32'),
                                             self.instrument.fine_sampling_factor,
                                             oversampling,
                                             numpy.ascontiguousarray(self.pointing.time),
                                             numpy.ascontiguousarray(self.pointing.ra),
                                             numpy.ascontiguousarray(self.pointing.dec),
                                             numpy.ascontiguousarray(self.pointing.pa),
                                             numpy.ascontiguousarray(self.pointing.chop),
                                             numpy.ascontiguousarray(self.pointing.masked, numpy.int8),
                                             numpy.ascontiguousarray(self.pointing.removed,numpy.int8),
                                             numpy.asfortranarray(self.instrument.detector_mask, numpy.int8),
                                             self.instrument.detector_corner.base.base.swapaxes(0,1).copy().T,
                                             self.instrument.distortion_yz.base.base.T,
                                             resolution)
        if status != 0: raise RuntimeError()
        header = _str2fitsheader(header)
        return header
   

#-------------------------------------------------------------------------------


class PacsSimulation(_Pacs):
    """
    This class creates a simulated PACS observation.
    """
    def __init__(self, pointing, band, mode='prime', fine_sampling_factor=1, detector_mask='calibration', reject_bad_line=False, policy_inscan='keep', policy_turnaround='keep', policy_other='remove', policy_invalid='mask'):
        band = band.lower()
        if band not in ('blue', 'green', 'red'):
            raise ValueError("Band is not 'blue', 'green', nor 'red'.")

        mode = mode.lower()
        if mode not in ('prime', 'parallel', 'transparent'):
            raise ValueError("Observing mode is not 'prime', 'parallel', nor 'transparent'.")
        
        if pointing.header is not None and 'compression_factor' in pointing.header:
            compression_factor = pointing.header['compression_factor']
        else:
            compression_factor = 8 if mode == 'parallel' and band != 'red' else 1 if mode == 'transparent' else 4

        detector_mask = self._get_detector_mask(band, detector_mask, mode == 'transparent', reject_bad_line)
        ftype = get_default_dtype_float()

        # store pointing information
        if not hasattr(pointing, 'chop'):
            pointing.chop = numpy.zeros(pointing.size, ftype)
        self.pointing = pointing
        self.pointing.removed = policy_inscan == 'remove' and self.pointing.info == Pointing.INSCAN or \
                                policy_turnaround == 'remove' and self.pointing.info == Pointing.TURNAROUND

        # store instrument information
        detector_center, detector_corner, detector_area, distortion_yz, oflat, dflat, responsivity, active_fraction, status = tmf.pacs_info_instrument(band, numpy.asfortranarray(detector_mask, numpy.int8))
        if status != 0: raise RuntimeError()
        self.instrument = Instrument('PACS/'+band.capitalize(),detector_mask)
        self.instrument.active_fraction = active_fraction
        self.instrument.band = band
        self.instrument.reject_bad_line = reject_bad_line
        self.instrument.fine_sampling_factor = fine_sampling_factor
        self.instrument.detector_center = detector_center.T.swapaxes(0,1).copy().view(dtype=[('u',ftype),('v',ftype)]).view(numpy.recarray)
        self.instrument.detector_corner = detector_corner.T.swapaxes(0,1).copy().view(dtype=[('u',ftype),('v',ftype)]).view(numpy.recarray)
        self.instrument.detector_area = Map(numpy.ascontiguousarray(detector_area), unit='arcsec^2/detector', origin='upper')
        self.instrument.distortion_yz = distortion_yz.T.view(dtype=[('y',ftype), ('z',ftype)]).view(numpy.recarray)
        self.instrument.flatfield = FlatField(oflat, dflat)
        self.instrument.responsivity = Quantity(responsivity, 'V/Jy')

        self.slice = numpy.recarray(1, dtype=[('filename', 'S256'), ('nsamples_all', int), ('mode', 'S32'), ('compression_factor', int), ('unit', 'S32'), ('ra', float), ('dec', float), ('cam_angle', float), ('scan_angle', float), ('scan_length', float), ('scan_nlegs', int), ('scan_step', float), ('scan_speed', float)])
        self.slice.filename = ''
        self.slice.nsamples_all = self.pointing.size
        self.slice.mode = mode
        self.slice.compression_factor = compression_factor
        self.slice.unit = ''
        for field in ('ra', 'dec', 'cam_angle', 'scan_angle', 'scan_nlegs', 'scan_length', 'scan_step', 'scan_speed'):
            self.slice[field] = pointing.header[field] if field in pointing.header else 0
        self.slice.ninscans = numpy.sum(self.pointing.info == Pointing.INSCAN)
        self.slice.nturnarounds = numpy.sum(self.pointing.info == Pointing.TURNAROUND)
        self.slice.nothers = numpy.sum(self.pointing.info == Pointing.OTHER)
        self.slice.ninvalids = 0
        
        # store policy
        self.policy = MaskPolicy('inscan,turnaround,other,invalid', 'keep,keep,remove,mask', 'Frame Policy')

        self._status = _write_status(self)

        print(self)

    def save(self, filename, tod):
        
        if numpy.rank(tod) != 3:
            tod = self.unpack(tod)

        nsamples = numpy.sum(self.slice.nsamples_all)
        if nsamples != tod.shape[-1]:
            raise ValueError("The input Tod has a number of samples'" + str(tod.shape[-1]) + "' incompatible with that of this observation '" + str(nsamples) + "'.")

        _write_status(self, filename)
        if tod.header is None:
            header = create_fitsheader(tod, extname='Signal')
        else:
            header = tod.header.copy()
            header.update('EXTNAME', 'Signal')

        if tod.unit != '':
            header.update('QTTY____', tod.unit)

        pyfits.append(filename, tod, header)
        if tod.mask is not None:
            print 'Warning: the saving of the tod mask is not implemented.'
        
   
#-------------------------------------------------------------------------------


class PacsMultiplexing(AcquisitionModel):
    """
    Performs the multiplexing of the PACS subarrays. The subarray columns are read one after the
    other, in a 0.025s cycle (40Hz).
    Author: P. Chanial
    """
    def __init__(self, obs, description=None):
        AcquisitionModel.__init__(self, description)
        self.fine_sampling_factor = obs.instrument.fine_sampling_factor
        self.ij = obs.instrument.ij

    def direct(self, signal, reusein=False, reuseout=False):
        signal, shapeout = self.validate_input_direct(Tod, signal, reusein)
        output = self.validate_output_direct(Tod, shapeout, reuseout)
        output.nsamples = tuple(numpy.divide(signal.nsamples, self.fine_sampling_factor))
        tmf.pacs_multiplexing_direct(signal.T, output.T, self.fine_sampling_factor, self.ij)
        return output

    def transpose(self, signal, reusein=False, reuseout=False):
        signal, shapein = self.validate_input_transpose(Tod, signal, reusein)
        output = self.validate_output_transpose(Tod, shapein, reuseout)
        output.nsamples = tuple(numpy.multiply(signal.nsamples, self.fine_sampling_factor))
        tmf.pacs_multiplexing_transpose(signal.T, output.T, self.fine_sampling_factor, self.ij)
        return output

    def validate_shapein(self, shapein):
        if shapein is None:
            return None
        if shapein[1] % self.fine_sampling_factor != 0:
            raise ValidationError('The input timeline size ('+str(shapein[1])+') is not an integer times the fine sampling factor ('+str(self.fine_sampling_factor)+').')
        shapeout = list(shapein)
        shapeout[1] = shapeout[1] / self.fine_sampling_factor
        return tuple(shapeout)

    def validate_shapeout(self, shapeout):
        if shapeout is None:
            return
        super(PacsMultiplexing, self).validate_shapeout(shapeout)
        shapein = list(shapeout)
        shapein[1] = shapein[1] * self.fine_sampling_factor
        return tuple(shapein)


#-------------------------------------------------------------------------------


def pacs_plot_scan(patterns, title=None, new_figure=True):
    if type(patterns) not in (tuple, list):
        patterns = (patterns,)

    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))

    for ifile, file in enumerate(files):
        try:
            hdu = pyfits.open(file)['STATUS']
        except Exception as error:
            print("Warning: Cannot extract status from file '"+file+"': "+str(error))
            continue

        while True:
            try:
                status = hdu.data
                break
            except IndexError:
                pass

        if ifile == 0:
            image = plot_scan(status.RaArray, status.DecArray, title=title, new_figure=new_figure)
        else:
            x, y = image.topixel(status.RaArray, status.DecArray)
            p = pyplot.plot(x, y, linewidth=2)
            pyplot.plot(x[0], y[0], 'o', color = p[0]._color)


#-------------------------------------------------------------------------------


def pacs_preprocess(obs,
                    tod,
                    projection_method='sharp',
                    header=None,
                    oversampling=True,
                    npixels_per_sample=0,
                    deglitching_hf_length=20,
                    deglitching_nsigma=5.,
                    hf_length=30000,
                    transparent_mode_compression_factor=1):
    """
    deglitch, filter and potentially compress if the observation is in transparent mode
    """
    projection = Projection(obs,
                            method='sharp',
                            header=header,
                            oversampling=False,
                            npixels_per_sample=npixels_per_sample)
    tod_filtered = filter_median(tod, deglitching_hf_length)
    tod.mask = deglitch_l2mad(tod_filtered,
                              projection,
                              nsigma=deglitching_nsigma)
    tod = filter_median(tod, hf_length)
    masking = Masking(tod.mask)
    tod = masking(tod)
    
    # get the proper projector if necessary
    if projection is None or projection_method != 'sharp' or oversampling and numpy.any(obs.slice.compression_factor * obs.instrument.fine_sampling_factor > 1):
        projection = Projection(obs,
                                method=projection_method,
                                oversampling=oversampling,
                                header=header,
                                npixels_per_sample=npixels_per_sample)

    # bail out if not in transparent mode
    if all(obs.slice[0].compression_factor != 1) or transparent_mode_compression_factor == 1:
        if oversampling:
            model = CompressionAverage(obs.slice.compression_factor) * projection
        else:
            model = projection
        map_mask = model.T(Tod(tod.mask, nsamples=tod.nsamples))
        model = masking * model
        return tod, model, mapper_naive(tod, model), map_mask

    # compress the transparent observation
    compression = CompressionAverage(transparent_mode_compression_factor)
    todc = compression(tod)
    mask = compression(tod.mask)
    mask[mask != 0] = 1
    todc.mask = numpy.array(mask, dtype='uint8')
    maskingc = Masking(todc.mask)

    model = compression * projection
    map_mask = model.T(Tod(tod.mask, nsamples=tod.nsamples, copy=False))
    model = masking * model

    return todc, model, mapper_naive(todc, model), map_mask


#-------------------------------------------------------------------------------


def pacs_create_scan(ra0, dec0, cam_angle=0., scan_angle=0., scan_length=30., scan_nlegs=3, scan_step=20., scan_speed=10., 
                     compression_factor=4):
    if int(compression_factor) not in (1, 4, 8):
        raise ValueError("Input compression_factor must be 1, 4 or 8.")
    scan = create_scan(ra0, dec0, PACS_ACCELERATION, PACS_SAMPLING * compression_factor, scan_angle=scan_angle,
                       scan_length=scan_length, scan_nlegs=scan_nlegs, scan_step=scan_step, scan_speed=scan_speed,
                       dtype=PACS_POINTING_DTYPE)
    scan.header.update('HIERARCH cam_angle', cam_angle)
    scan.chop = 0.
    return scan


#-------------------------------------------------------------------------------


def _files2tmf(filename):
    nfilenames = len(filename)
    length = max(len(f) for f in filename)
    filename_ = ''
    for f in filename:
        filename_ += f + (length-len(f))*' '
    return filename_, nfilenames


#-------------------------------------------------------------------------------


def _split_observation(nobservations, ndetectors):
    nnodes  = MPI.COMM_WORLD.Get_size()
    nthreads = tmf.info_nthreads()

    # number of observations. They should approximatively be of the same length
    nx = nobservations

    # number of detectors, grouped by the number of cpu cores
    ny = int(numpy.ceil(float(ndetectors) / nthreads))

    # we start with the miminum blocksize and increase it until we find a configuration that covers all the observations
    blocksize = int(numpy.ceil(float(nx * ny) / nnodes))
    while True:
        # by looping over x first, we favor larger number of detectors and fewer number of observations per processor, to minimise inter-processor communication in case of correlations between detectors
        for xblocksize in range(1, blocksize+1):
            if float(blocksize) / xblocksize != blocksize // xblocksize:
                continue
            yblocksize = int(blocksize // xblocksize)
            nx_block = int(numpy.ceil(float(nx) / xblocksize))
            ny_block = int(numpy.ceil(float(ny) / yblocksize))
            if nx_block * ny_block <= nnodes:
                break
        if nx_block * ny_block <= nnodes:
            break
        blocksize += 1

    rank = MPI.COMM_WORLD.Get_rank()

    ix = rank // ny_block
    iy = rank %  ny_block

    # check that the processor has something to do
    if ix >= nx_block:
        iobservation = slice(0,0)
        idetector = slice(0,0)
    else:
        iobservation = slice(ix * xblocksize, (ix+1) * xblocksize)
        idetector    = slice(iy * yblocksize * nthreads, (iy+1) * yblocksize * nthreads)

    return iobservation, idetector
        

#-------------------------------------------------------------------------------


def _str2fitsheader(string):
    """
    Convert a string into a pyfits.Header object
    All cards are extracted from the input string until the END keyword is reached.
    """
    header = pyfits.Header()
    cards = header.ascardlist()
    iline = 0
    while (iline*80 < len(string)):
        line = string[iline*80:(iline+1)*80]
        if line[0:3] == 'END': break
        cards.append(pyfits.Card().fromstring(line))
        iline += 1
    return header


#-------------------------------------------------------------------------------


def _write_status(obs, filename=None):

    s = obs.slice[0]

    if any(obs.slice.compression_factor != obs.slice[0].compression_factor):
        raise ValueError('Unable to save into a single file. The observations do not have the same compression factor.')
    compression_factor = s.compression_factor

    if any(obs.slice.mode != obs.slice[0].mode):
        raise ValueError('Unable to save into a single file. The observations do not have the same observing mode.')
    mode = s.mode
    band_status = {'blue':'BS', 'green':'BL', 'red':'R '}[obs.instrument.band]
    band_type   = {'blue':'BS', 'green':'BL', 'red':'RS'}[obs.instrument.band]

    cusmode = {'prime':'PacsPhoto', 'parallel':'SpirePacsParallel', 'transparent':'__PacsTranspScan', 'unknown':'__Calibration'}
    if mode == 'prime' or obs.instrument.band == 'red':
        comp_mode = 'Photometry Default Mode'
    elif mode == 'parallel':
        comp_mode = 'Photometry Double Compression Mode'
    elif mode == 'transparent':
        comp_mode = 'Photometry Lossless Compression Mode'
    else:
        comp_mode = ''

    if obs.slice[0].scan_speed == 10.:
        scan_speed = 'low'
    elif obs.slice[0].scan_speed == 20.:
        scan_speed = 'medium'
    elif obs.slice[0].scan_speed == 60.:
        scan_speed = 'high'
    else:
        scan_speed = str(obs.slice[0].scan_speed)
        
    p = obs.pointing
    if p.size != numpy.sum(obs.slice.nsamples_all):
        raise ValueError('The pointing and slice attribute are incompatible. This case should not happen.')

    # get status
    table = numpy.recarray(p.size, dtype=[('BBID', numpy.int64), ('FINETIME', numpy.int64), ('BAND', 'S2'), ('CHOPFPUANGLE', numpy.float64), ('RaArray', numpy.float64), ('DecArray', numpy.float64), ('PaArray', numpy.float64)])
    table.BAND     = band_status
    table.FINETIME = numpy.round(p.time*1000000.)
    table.RaArray  = p.ra
    table.DecArray = p.dec
    table.PaArray  = p.pa
    table.CHOPFPUANGLE = 0. if not hasattr(p, 'chop') else p.chop
    table.BBID = 0
    #XXX Numpy ticket #1645
    table.BBID[p.info == Pointing.INSCAN] = 0xcd2 << 16
    table.BBID[p.info == Pointing.TURNAROUND] = 0x4000 << 16

    if filename is None:
        return table

    fits = pyfits.HDUList()

    # Primary header
    cc = pyfits.createCard
    
    header = pyfits.Header([
            cc('simple', True), 
            cc('BITPIX', 32), 
            cc('NAXIS', 0), 
            cc('EXTEND', True, 'May contain datasets'), 
            cc('TYPE', 'HPPAVG'+band_type, 'Product Type Identification'), 
            cc('CREATOR', 'TAMASIS v' + __version__, 'Generator of this file'), 
            cc('INSTRUME', 'PACS', 'Instrument attached to this file'), 
            cc('TELESCOP', 'Herschel Space Observatory', 'Name of telescope'),
            cc('OBS_MODE', 'Scan map', 'Observation mode name'),
            cc('RA', s.ra),
            cc('DEC', s.dec),
            cc('EQUINOX', 2000., 'Equinox of celestial coordinate system'),
            cc('RADESYS', 'ICRS', 'Coordinate reference frame for the RA and DEC'),
            cc('CUSMODE', cusmode[mode], 'CUS observation mode'),
            cc('META_0', obs.instrument.shape[0]),
            cc('META_1', obs.instrument.shape[1]), 
            cc('META_2', obs.instrument.band.title()+' Photometer'), 
            cc('META_3', ('Floating Average  : ' + str(compression_factor)) if compression_factor > 1 else 'None'), 
            cc('META_4', comp_mode),
            cc('META_5', s.scan_angle),
            cc('META_6', s.scan_length),
            cc('META_7', s.scan_nlegs),
            cc('META_8', scan_speed),
            cc('HIERARCH key.META_0', 'detRow'), 
            cc('HIERARCH key.META_1', 'detCol'), 
            cc('HIERARCH key.META_2', 'camName'), 
            cc('HIERARCH key.META_3', 'algorithm'), 
            cc('HIERARCH key.META_4', 'compMode'),
            cc('HIERARCH key.META_5', 'mapScanAngle'),
            cc('HIERARCH key.META_6', 'mapScanLegLength'),
            cc('HIERARCH key.META_7', 'mapScanNumLegs'),
            cc('HIERARCH key.META_8', 'mapScanSpeed'),
            ])

    hdu = pyfits.PrimaryHDU(None, header)
    fits.append(hdu)
    
    status = pyfits.BinTableHDU(table, None, 'STATUS')
    fits.append(status)
    fits.writeto(filename, clobber=True)

    return table
