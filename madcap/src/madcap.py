import numpy as np
import pyfits
import re
from tamasis.core import *
from tamasis.observations import *

__all__ = [ 'MadMap1Observation' ]

class MadMap1Observation(Observation):
    """Class for the handling of an observation in the MADMAP1 format"""
    def __init__(self, todfile, invnttfile, mapmaskfile, convert, ndetectors,
                 missing_value=None):

        # Get information from files
        nslices, status = tmf.madmap1_nslices(invnttfile, ndetectors)
        if status != 0: raise RuntimeError()
        npixels_per_sample, nsamples, ncorrelations, status = tmf.madmap1_info(\
            todfile, invnttfile, convert, ndetectors, nslices)
        if status != 0: raise RuntimeError()

        m=re.search(r'(?P<filename>.*)\[(?P<extname>\w+)\]$', mapmaskfile)
        if m is None:
            mask = pyfits.fitsopen(mapmaskfile)[0].data
        else:
            filename = m.group('filename')
            extname  = m.group('extname')
            mask = pyfits.fitsopen(filename)[extname].data
        if mask is None:
            raise IOError('HDU '+mapmaskfile+' has no data.')
        mapmask = np.zeros(mask.shape, dtype='int8')
        if missing_value is None:
            mapmask[mask != 0] = 1
        elif np.isnan(missing_value):
            mapmask[np.isnan(mask)] = 1
        elif np.isinf(missing_value):
            mapmask[np.isinf(mask)] = 1
        else:
            mapmask[mask == missing_value] = 1

        # Store instrument information
        self.instrument = Instrument('Unknown', np.zeros((ndetectors,)))

        # Store observation information
        class MadMap1ObservationInfo(object):
            pass
        self.info = MadMap1ObservationInfo()
        self.info.todfile = todfile
        self.info.invnttfile = invnttfile
        self.info.ncorrelations = ncorrelations
        self.info.npixels_per_sample = npixels_per_sample
        self.info.mapmaskfile = mapmaskfile
        self.info.convert = convert
        self.info.missing_value = missing_value
        self.info.mapmask = mapmask

        # Store slice information
        self.slice = np.recarray(nslices, dtype=[('nsamples_all', int),
                                                 ('invnttfile', 'S256')])
        self.slice.nsamples_all = nsamples
        self.slice.nfinesamples = nsamples
        self.slice.invnttfile = [invnttfile+'.'+str(i) for i in range(nslices)]

        # Store pointing information
        self.pointing = np.recarray(np.sum(nsamples), [('removed', np.bool_)])
        self.pointing.removed = False

    def get_pointing_matrix(self, header, resolution, npixels_per_sample,
                            method=None, oversampling=False):
        """
        Method to get the pointing matrix.
        """
        if npixels_per_sample not in (0, self.info.npixels_per_sample):
            raise ValueError('The npixels_per_sample value is incompatible wi' \
                             'th the MADMAP1 file.')
        if header is not None:
            raise ValueError('The map header cannot be specified for MADmap1 ' \
                             'observations.')
        if resolution is not None:
            raise ValueError('The map resolution cannot be specified for MADm' \
                             'ap1 observations.')
        header = pyfits.Header()
        header.update('simple', True)
        header.update('bitpix', -64)
        header.update('extend', True)
        header.update('naxis', 1)
        header.update('naxis1', np.sum(self.info.mapmask == 0))

        ndetectors = self.get_ndetectors()
        nsamples   = self.get_nsamples()
        tod = Tod.zeros((ndetectors,nsamples))

        sizeofpmatrix = self.info.npixels_per_sample * tod.size
        print('Info: Allocating '+str(sizeofpmatrix/2.**17)+' MiB for the pointing matrix.')
        pmatrix = np.zeros(sizeofpmatrix, dtype=np.int64)
        status = tmf.madmap1_read_tod(self.info.todfile, self.info.invnttfile, self.info.convert, self.info.npixels_per_sample, tod.T, pmatrix)
        if status != 0: raise RuntimeError()
        return pmatrix, header, ndetectors, nsamples, \
               self.info.npixels_per_sample, (None, None), (None, None)

    def get_tod(self, unit=None):
        """
        Method to get the Tod from this observation
        """
        tod = Tod.zeros((self.get_ndetectors(), self.get_nsamples()))
        sizeofpmatrix = self.info.npixels_per_sample * tod.size
        pmatrix = np.zeros(sizeofpmatrix, dtype=int)
        status = tmf.madmap1_read_tod(self.info.todfile, self.info.invnttfile,
            self.info.convert, self.info.npixels_per_sample, tod.T, pmatrix)
        if status != 0: raise RuntimeError()
        if unit is not None:
            tod.unit = unit
        return tod

    def get_filter_uncorrelated(self):
        """
        Method to get the invNtt for uncorrelated detectors.
        """
        data, nsamples, status = tmf.madmap1_read_filter(self.info.invnttfile,
            self.info.convert, self.info.ncorrelations, self.get_ndetectors(),
            self.slice.size)
        if status != 0: raise RuntimeError()
        return data.T

    def get_nsamples(self):
        nsamples = np.sum(~self.pointing.removed)
        if nsamples != np.sum(self.pointing.size):
            raise ValueError("The pointing attribute 'removed' cannot be set " \
                             'to True.')
        return self.slice.nsamples_all
