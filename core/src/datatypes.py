import kapteyn.maputils
import matplotlib
import matplotlib.pyplot as pyplot
import numpy as np
import pickle
import pyfits
import StringIO
    
try:
    import ds9
    _imported_ds9 = True
except:
    _imported_ds9 = False

import tamasisfortran as tmf

from functools import reduce
from .numpyutils import _my_isscalar
from .quantity import Quantity, UnitError, _extract_unit, _strunit

__all__ = [ 'FitsArray', 'Map', 'Tod', 'create_fitsheader' ]


class FitsArray(Quantity):

    __slots__ = ('_header',)
    def __new__(cls, data, header=None, unit=None, derived_units=None,
                dtype=None, copy=True, order='C', subok=False, ndmin=0):

        if type(data) is str:
            ihdu = 0
            fits = pyfits.open(data)
            while True:
                try:
                    hdu = fits[ihdu]
                except IndexError:
                    raise IOError('The FITS file has no data.')
                if hdu.header['NAXIS'] == 0:
                    ihdu += 1
                    continue
                if hdu.data is not None:
                    break
            data = hdu.data
            header = hdu.header
            copy = False
            if unit is None:
                if 'BUNIT' in header:
                    unit = header['BUNIT']
                elif 'QTTY____' in header:
                    unit = header['QTTY____'] # HCSS crap
            del header['BUNIT']
            try:
                derived_units = fits['derived_units'].data
                derived_units = pickle.loads(str(derived_units.data))
            except KeyError:
                pass

        # get a new FitsArray instance (or a subclass if subok is True)
        result = Quantity.__new__(cls, data, unit, derived_units, dtype, copy,
                                  order, True, ndmin)
        if not subok and result.__class__ is not cls:
            result = result.view(cls)

        # copy header attribute
        if header is not None:
            result.header = header
        elif hasattr(data, '_header') and \
             data._header.__class__ is pyfits.Header:
            if copy:
                result._header = data._header.copy()
            else:
                result._header = data._header
        elif not np.iscomplexobj(result):
            result._header = create_fitsheader(result)
        else:
            result._header = None

        return result

    def __array_finalize__(self, array):
        Quantity.__array_finalize__(self, array)
        self._header = getattr(array, '_header', None)

    @staticmethod
    def empty(shape, header=None, unit=None, derived_units=None, dtype=None,
              order=None):
        return FitsArray(np.empty(shape, dtype, order), header, unit,
                         derived_units, dtype, copy=False)

    @staticmethod
    def ones(shape, header=None, unit=None, derived_units=None, dtype=None,
             order=None):
        return FitsArray(np.ones(shape, dtype, order), header, unit,
                         derived_units, dtype, copy=False)

    @staticmethod
    def zeros(shape, header=None, unit=None, derived_units=None, dtype=None,
              order=None):
        return FitsArray(np.zeros(shape, dtype, order), header, unit,
                         derived_units, dtype, copy=False)

    def has_wcs(self):
        """
        Returns True is the array has a FITS header with a defined World
        Coordinate System.
        """
        if self.header is None:
            return False

        required = 'CRPIX,CRVAL,CTYPE'.split(',')
        keywords = np.concatenate(
            [(lambda i: [r+str(i+1) for r in required])(i) 
             for i in range(self.header['NAXIS'])])

        return all([k in self.header for k in keywords])

    @property
    def header(self):
        return self._header

    @header.setter
    def header(self, header):
        if header is not None and not isinstance(header, pyfits.Header):
            raise TypeError('Incorrect type for the input header (' + \
                            str(type(header))+').')
        self._header = header

    def tofile(self, fid, sep='', format='%s'):
        super(FitsArray,self).tofile(fid, sep, format)

    def save(self, filename, fitskw={}):
        """Save a FitsArray instance to a fits file given a filename
       
        If the same file already exist it overwrites it.
        """

        if self.header is not None:
            header = self.header.copy()
        else:
            header = create_fitsheader(self)
       
        if len(self._unit) != 0:
            header.update('BUNIT', self.unit)

        for k,v in fitskw.items():
            if hasattr(self, k):
                header.update(v, str(getattr(self, k)))

        if np.rank(self) == 0:
            value = self.reshape((1,))
        else:
            value = self.T if np.isfortran(self) else self
        hdu = pyfits.PrimaryHDU(value, header)
        hdu.writeto(filename, clobber=True)
        if not isinstance(self, Map) and not isinstance(self, Tod):
            _save_derived_units(filename, self.derived_units)

    def imsave(self, filename, colorbar=True, **kw):
        is_interactive = matplotlib.is_interactive()
        matplotlib.interactive(False)
        dpi = 80.
        figsize = np.clip(np.max(np.array(self.shape[::-1])/dpi), 8, 50)
        figsize = (figsize + (2 if colorbar else 0), figsize)
        fig = pyplot.figure(figsize=figsize, dpi=dpi)
        self.imshow(colorbar=colorbar, new_figure=False, **kw)
        fig = pyplot.gcf()
        fig.savefig(filename)
        matplotlib.interactive(is_interactive)

    def imshow(self, mask=None, title=None, colorbar=True, aspect=None,
               interpolation='nearest', origin=None, xlabel='', ylabel='',
               new_figure=True, **kw):
        """
        A simple graphical display function for the Tod class

        mask: array-like
            True means masked.
        """

        unfinite = ~np.isfinite(np.asarray(self))
        if mask is None:
            mask = unfinite
        else:
            mask = np.logical_or(mask, unfinite)

        data = np.ma.MaskedArray(np.asarray(self), mask=mask, copy=False)
        if np.iscomplexobj(data):
            data = abs(data)
        mean   = np.mean(data)
        stddev = np.std(data)
        # casting to float because of a bug numpy1.4 + matplotlib
        minval = float(max(mean - 2*stddev, np.min(data)))
        maxval = float(min(mean + 5*stddev, np.max(data)))

        if new_figure:
            fig = pyplot.figure()
        else:
            fig = pyplot.gcf()
        fontsize = 12. * fig.get_figheight() / 6.125

        image = pyplot.imshow(data, aspect=aspect, interpolation=interpolation,
                              origin=origin, **kw)
        image.set_clim(minval, maxval)

        ax = pyplot.gca()
        ax.set_xlabel(xlabel, fontsize=fontsize)
        ax.set_ylabel(ylabel, fontsize=fontsize)
        for tick in ax.xaxis.get_major_ticks():
            tick.label1.set_fontsize(fontsize)
        for tick in ax.yaxis.get_major_ticks():
            tick.label1.set_fontsize(fontsize)

        if title is not None:
            pyplot.title(title, fontsize=fontsize)
        if colorbar:
            colorbar = pyplot.colorbar()
            for tick in colorbar.ax.get_yticklabels():
                tick.set_fontsize(fontsize)

        pyplot.draw()
        return image

    def ds9(self, xpamsg=None, origin=None, new=True, **keywords):
        """
        Display the array using ds9.

        The ds9 process will be given an random id. By default, the
        following access point are set before the array is loaded:
            -cmap heat
            -scale scope local
            -scale mode 99.5
            -zoom to fit
        Other access points can be set before the data is loaded though
        the keywords (see examples below).
        After the array is loaded, the map's header is set and the user
        may add other XPA messages through the xpamsg argument or by
        setting them through the returned ds9 instance.

        Parameters
        ----------
        xpamsg : string or tuple of string
            XPA access point message to be set after the array is loaded.
            (see http://hea-www.harvard.edu/RD/ds9/ref/xpa.html).
        origin: string
            Set origin to 'upper' for Y increasing downwards
        new: boolean
            If true, open the array in a new ds9 instance.
        **keywords : string or tuple of string
            Specify more access points to be set before array loading.
            a keyword such as 'height=400' will be appended to the command
            that launches ds9 in the form 'ds9 [...] -height 400'

        Returns
        -------
        The returned object is a ds9 instance. It can be manipulated using
        XPA access points.

        Examples
        --------
        >>> m = Map('myfits.fits')
        >>> d=m.ds9('saveimage png myfits.png', scale='histequ', 
                    cmap='invert yes', height=400)
        >>> d.set('exit')
        """
        if not _imported_ds9:
            raise RuntimeError('The library pyds9 has not been installed.')
        import ds9, os, time, sys, uuid, xpa

        id = None
        if not new:
            list = ds9.ds9_targets()
            if list is not None:
                id = list[-1]

        if id is None:
            if 'cmap' not in keywords:
                keywords['cmap'] = 'heat'

            if 'zoom' not in keywords:
                keywords['zoom'] = 'to fit'

            if 'scale' not in keywords:
                keywords['scale'] = ('scope local', 'mode 99.5')

            if origin == 'upper' or \
               'orient' not in keywords and self.origin == 'upper':
                keywords['orient'] = 'y'

            wait = 10

            id = 'ds9_' + str(uuid.uuid1())[4:8]

            command = 'ds9 -title ' + id

            for k,v in keywords.items():
                k = str(k)
                if type(v) is not tuple:
                    v = (v,)
                command += reduce(lambda x,y: \
                                  str(x) + ' -' + k + ' ' + str(y),v,'')

            os.system(command + '&')

            # start the xpans name server
            if xpa.xpaaccess("xpans", None, 1) == None:
                _cmd = None
                # look in install directories
                for _dir in sys.path:
                    _fname = os.path.join(_dir, "xpans")
                    if os.path.exists(_fname):
                        _cmd = _fname + " -e &"
                if _cmd:
                    os.system(_cmd)

            for i in range(wait):
                list = xpa.xpaaccess(id, None, 1024)
                if list: break
                time.sleep(1)
            if not list:
                raise ValueError('No active ds9 running for target: %s' % list)

        # get ds9 instance with given id
        d = ds9.ds9(id)
        d.set_np2arr(self.view(np.ndarray).T)

        if self.has_wcs():
            d.set('wcs append', str(self.header))
    
        if xpamsg is not None:
            if isinstance(xpamsg, str):
                xpamsg = (xpamsg,)
            for v in xpamsg:
                d.set(v)

        return d


class Map(FitsArray):

    __slots__ = ('coverage', 'error', 'origin')

    """
    Represent a map, complemented with unit and FITS header.
    """
    def __new__(cls, data,  header=None, unit=None, derived_units=None,
                coverage=None, error=None, origin=None, dtype=None, copy=True,
                order='C', subok=False, ndmin=0):

        # get a new Map instance (or a subclass if subok is True)
        result = FitsArray.__new__(cls, data, header, unit, derived_units,
                                   dtype, copy, order, True, ndmin)
        if not subok and result.__class__ is not cls:
            result = result.view(cls)

        if type(data) is str:
            if 'DISPORIG' in result.header:
                if origin is None:
                    origin = result.header['DISPORIG']
                del result.header['DISPORIG']
            try:
                if error is None: error = pyfits.open(data)['Error'].data
            except:
                pass
            try:
                if coverage is None: coverage = pyfits.open(data)['Coverage'].data
            except:
                pass

        if origin is not None:
            origin = origin.strip().lower()
            if origin not in ('upper', 'lower', 'none'):
                raise ValueError("Invalid origin '" + origin + "'. Expected v" \
                                 "alues are None, 'upper' or 'lower'.")
            if origin != 'none':
                result.origin = origin

        if error is not None:
            result.error = error
        elif copy and result.error is not None:
            result.error = result.error.copy()

        if coverage is not None:
            result.coverage = coverage
        elif copy and result.coverage is not None:
            result.coverage = result.coverage.copy()

        return result

    def __array_finalize__(self, array):
        FitsArray.__array_finalize__(self, array)
        self.coverage = getattr(array, 'coverage', None)
        self.error = getattr(array, 'error', None)
        self.origin = getattr(array, 'origin', 'lower')

    def __getitem__(self, key):
        item = super(Quantity, self).__getitem__(key)
        if not isinstance(item, Map):
            return item
        if item.coverage is not None:
            item.coverage = item.coverage[key]
        return item

    @property
    def header(self):
        return self._header

    @header.setter
    def header(self, header):
        if header is not None and not isinstance(header, pyfits.Header):
            raise TypeError('Incorrect type for the input header (' + \
                            str(type(header))+').')
        self._header = header

    @staticmethod
    def empty(shape, coverage=None, error=None, origin='lower', header=None,
              unit=None, derived_units=None, dtype=None, order=None):
        return Map(np.empty(shape, dtype, order), header, unit, derived_units,
                   coverage, error, origin, dtype, copy=False)

    @staticmethod
    def ones(shape, coverage=None, error=None, origin='lower', header=None,
             unit=None, derived_units=None, dtype=None, order=None):
        return Map(np.ones(shape, dtype, order), header, unit, derived_units,
                   coverage, error, origin, dtype, copy=False)

    @staticmethod
    def zeros(shape, coverage=None, error=None, origin='lower', header=None,
              unit=None, derived_units=None, dtype=None, order=None):
        return Map(np.zeros(shape, dtype, order), header, unit, derived_units,
                   coverage, error, origin, dtype, copy=False)

    def imshow(self, mask=None, title=None, new_figure=True, origin=None, **kw):
        """A simple graphical display function for the Map class"""

        if mask is None and self.coverage is not None:
            mask = self.coverage <= 0
        if mask is not None:
            data = np.array(self, copy=True)
            data[mask] = np.nan
        else:
            data = np.asarray(self)

        if origin is None:
            origin = self.origin

        # check if the map has no astrometry information
        if not self.has_wcs():
            if 'xlabel' not in kw:
                kw['xlabel'] = 'X'
            if 'ylabel' not in kw:
                kw['ylabel'] = 'Y'
            image = super(Map, self).imshow(title=title, new_figure=new_figure,
                                            origin=origin, **kw)
            return image

        fitsobj = kapteyn.maputils.FITSimage(externaldata=data,
                                             externalheader=self.header)
        if new_figure:
            fig = pyplot.figure()
            frame = fig.add_axes((0.1, 0.1, 0.8, 0.8))
        else:
            frame = pyplot.gca()
        if title is not None:
            frame.set_title(title)
        annim = fitsobj.Annotatedimage(frame, blankcolor='w')
        annim.Image(interpolation='nearest')
        grat = annim.Graticule()
        grat.setp_gratline(visible=False)
        annim.plot()
        annim.interact_imagecolors()
        annim.interact_toolbarinfo()
        annim.interact_writepos()
        pyplot.show()
        return annim

    def save(self, filename):
        FitsArray.save(self, filename, fitskw={'origin':'DISPORIG'})
        if self.error is not None:
            header = create_fitsheader(self.error, extname='Error')
            pyfits.append(filename, self.error, header)
        if self.coverage is not None:
            header = create_fitsheader(self.coverage, extname='Coverage')
            pyfits.append(filename, self.coverage, header)
        _save_derived_units(filename, self.derived_units)


#-------------------------------------------------------------------------------


class Tod(FitsArray):

    __slots__ = ('_mask', 'nsamples')

    def __new__(cls, data, mask=None, nsamples=None, header=None, unit=None,
                derived_units=None, dtype=None, copy=True, order='C',
                subok=False, ndmin=0):

        # get a new Tod instance (or a subclass if subok is True)
        result = FitsArray.__new__(cls, data, header, unit, derived_units,
                                   dtype, copy, order, True, ndmin)
        if not subok and result.__class__ is not cls:
            result = result.view(cls)
        
        # mask attribute
        if mask is np.ma.nomask:
            mask = None

        if mask is None and isinstance(data, str):
            try:
                mask = pyfits.open(data)['Mask'].data.view(np.bool8)
                copy = False
            except:
                pass

        if mask is None and hasattr(data, 'mask') and \
           data.mask is not np.ma.nomask:
            mask = data.mask

        if mask is not None:
            result._mask = np.array(mask, np.bool8, copy=copy)
        
        # nsamples attribute
        if type(data) is str and nsamples is None:
            if 'nsamples' in result.header:
                nsamples = result.header['nsamples'][1:-1].replace(' ', '')
                if len(nsamples) > 0:
                    nsamples = [int(float(x))
                                for x in nsamples.split(',') if x.strip() != '']
                del result.header['NSAMPLES']
        if nsamples is None:
            return result
        shape = validate_sliced_shape(result.shape, nsamples)
        result.nsamples = shape[-1]
        if type(result.nsamples) is not tuple:
            result.nsamples = (result.nsamples,)

        return result

    @property
    def mask(self):
        return self._mask

    @mask.setter
    def mask(self, mask):
        if mask is None or mask is np.ma.nomask:
            self._mask = None
            return

        # enforce bool8 dtype
        if not isinstance(mask, np.ndarray):
            mask = np.array(mask, np.bool8)
        elif mask.dtype.type != np.bool8:
            if mask.dtype.itemsize == 1:
                mask = mask.view(np.bool8)
            else:
                mask = np.asarray(mask, np.bool8)

        # handle the scalar case
        if np.rank(mask) == 0:
            if self._mask is None:
                func = np.zeros if mask == 0 else np.ones
                self._mask = func(self.shape, dtype=np.bool8)
            else:
                self._mask[:] = mask
            return

        # check shape compatibility
        if self.shape != mask.shape:
            raise ValueError("The input mask has a shape '" + str(mask.shape) +\
                "' incompatible with that of the Tod '" + str(self.shape) +"'.")
        
        self._mask = mask

    def __array_finalize__(self, array):
        FitsArray.__array_finalize__(self, array)
        self._mask = getattr(array, 'mask', None)
        self.nsamples = getattr(array, 'nsamples', () if np.rank(self) == 0 \
                        else (self.shape[-1],))

    def __getitem__(self, key):
        item = super(Quantity, self).__getitem__(key)
        if not isinstance(item, Tod):
            return item
        if item.mask is not None:
            item.mask = item.mask[key]
        if not isinstance(key, tuple):
            return item
        if len(key) > 1:
            if not isinstance(key[-1], slice):
                return item
            else:
                if key[-1].start is not None or key[-1].stop is not None or \
                   key[-1].step is not None:
                    item.nsamples = (item.shape[-1],)
        return item

    def reshape(self, newdims, order='C'):
        result = np.ndarray.reshape(self, newdims, order=order)
        if self.mask is not None:
            result.mask = self.mask.reshape(newdims, order=order)
        return result

    @staticmethod
    def empty(shape, mask=None, nsamples=None, header=None, unit=None,
              derived_units=None, dtype=None, order=None):
        shape = validate_sliced_shape(shape, nsamples)
        shape_flat = flatten_sliced_shape(shape)
        return Tod(np.empty(shape_flat, dtype, order), mask, shape[-1], header,
                   unit, derived_units, dtype, copy=False)

    @staticmethod
    def ones(shape, mask=None, nsamples=None, header=None, unit=None,
             derived_units=None, dtype=None, order=None):
        shape = validate_sliced_shape(shape, nsamples)
        shape_flat = flatten_sliced_shape(shape)
        return Tod(np.ones(shape_flat, dtype, order), mask, shape[-1], header,
                   unit, derived_units, dtype, copy=False)

    @staticmethod
    def zeros(shape, mask=None, nsamples=None, header=None, unit=None,
              derived_units=None, dtype=None, order=None):
        shape = validate_sliced_shape(shape, nsamples)
        shape_flat = flatten_sliced_shape(shape)
        return Tod(np.zeros(shape_flat, dtype, order), mask, shape[-1], header,
                   unit, derived_units, dtype, copy=False)
   
    def flatten(self, order='C'):
        """
        Return a copy of the array collapsed into one dimension.
        """
        result = super(self.__class__, self).flatten(order)
        result.nsamples = None
        return result

    def ravel(self, order='C'):
        """
        Return a flattened view of the array
        """
        result = super(self.__class__, self).ravel(order)
        result.nsamples = None
        return result
        
    def imshow(self, title=None, aspect='auto', **kw):
        """
        A simple graphical display function for the Map class
        """

        xlabel = 'Sample'
        ylabel = 'Detector number'
        image = super(Tod, self).imshow(mask=self.mask, title=title,
                                        origin='upper', xlabel=xlabel,
                                        ylabel=ylabel, aspect=aspect, **kw)
        return image

    def __str__(self):
        if np.rank(self) == 0:
            if np.iscomplexobj(self):
                return 'Tod ' + str(complex(self))
            else:
                return 'Tod ' + str(float(self))
        output = 'Tod ['
        if np.rank(self) > 1:
            output += str(self.shape[-2])+' detector'
            if self.shape[-2] > 1:
                output += 's'
            output += ', '
        output += str(self.shape[-1]) + ' sample'
        if self.shape[-1] > 1:
            output += 's'
        nslices = len(self.nsamples)
        if nslices > 1:
            strsamples = ','.join((str(self.nsamples[i])
                                   for i in range(nslices)))
            output += ' in ' + str(nslices) + ' slices ('+strsamples+')'
        return output + ']'

    def save(self, filename):
        FitsArray.save(self, filename, fitskw={'nsamples':'NSAMPLES'})
        if self.mask is None:
            return
        header = create_fitsheader(self.mask, extname='Mask')
        pyfits.append(filename, self.mask.view(np.uint8), header)
        _save_derived_units(filename, self.derived_units)


#-------------------------------------------------------------------------------


def create_fitsheader(array, extname=None, crval=(0.,0.), crpix=None,
                      ctype=('RA---TAN','DEC--TAN'), cunit='deg', cd=None,
                      cdelt=None, naxis=None):
    """
    Return a FITS header

    Parameters
    ----------
    array : array_like
        An array from which the dimensions will be extracted. Note that
        by FITS convention, the dimension along X is the second value 
        of the array shape and that the dimension along the Y axis is 
        the first one. If None is specified, naxis keyword must be set
    extname : None or string
        if a string is specified ('' can be used), the returned header
        type will be an Image HDU (otherwise a Primary HDU)
    crval : 2 element array, optional
        Reference pixel values (FITS convention)
    crpix : 2 element array, optional
        Reference pixel (FITS convention)
    ctype : 2 element string array, optional
        Projection types
    cunit : string or 2 element string array
        Units of the CD matrix (default is degrees/pixel)
    cd : 2 x 2 array
        Astrometry parameters
            CD1_1 CD1_2
            CD2_1 CD2_2
    cdelt : 2 element array
        Physical increment at the reference pixel
    naxis : 2 element array
        (NAXIS1,NAXIS2) tuple, to be specified only if array argument is None

    Examples
    --------
    >>> map = Map.ones((10,100), unit='Jy/pixel')
    >>> map.header = create_fitsheader(map, cd=[[-1,0],[0,1]])
    """

    if array is None:
        if naxis is None:
            raise ValueError('An array argument or naxis keyword should be sp' \
                             'ecified.')
        typename = 'float64'
    else:
        if not isinstance(array, np.ndarray):
            raise TypeError('The input is not an ndarray.')
        naxis = tuple(reversed(array.shape))
        if array.dtype.itemsize == 1:
            typename = 'uint8'
        elif array.dtype.names is not None:
            typename = None
        else:
            typename = array.dtype.name

    if type(naxis) not in (list, tuple):
        naxis = (naxis,)
    numaxis = len(naxis)

    if extname is None:
        card = pyfits.createCard('simple', True)
    else:
        card = pyfits.createCard('xtension', 'IMAGE', 'Image extension')
    header = pyfits.Header([card])
    if typename is not None:
        header.update('bitpix', pyfits.PrimaryHDU.ImgCode[typename],
                      'array data type')
    header.update('naxis', numaxis, 'number of array dimensions')
    for dim in range(numaxis):
        header.update('naxis'+str(dim+1), naxis[dim])
    if extname is None:
        header.update('extend', True)
    else:
        header.update('pcount', 0, 'number of parameters')
        header.update('gcount', 1, 'number of groups')
        header.update('extname', extname)

    if cd is not None:
        cd = np.asarray(cd, dtype=np.float64)
        if cd.shape != (2,2):
            raise ValueError('The CD matrix is not a 2x2 matrix.')
    else:
        if cdelt is None:
            return header
        if _my_isscalar(cdelt):
            cdelt = (-cdelt, cdelt)
        cd = np.array(((cdelt[0], 0), (0,cdelt[1])))

    crval = np.asarray(crval, dtype=np.float64)
    if crval.size != 2:
        raise ValueError('CRVAL does not have two elements.')

    if crpix is None:
        crpix = (np.array(naxis) + 1) / 2.
    else:
        crpix = np.asarray(crpix, dtype=np.float64)
    if crpix.size != 2:
        raise ValueError('CRPIX does not have two elements.')

    ctype = np.asarray(ctype, dtype=np.string_)
    if ctype.size != 2:
        raise ValueError('CTYPE does not have two elements.')

    if _my_isscalar(cunit):
        cunit = (cunit, cunit)
    cunit = np.asarray(cunit, dtype=np.string_)
    if cunit.size != 2:
        raise ValueError('CUNIT does not have two elements.')

    header.update('crval1', crval[0])
    header.update('crval2', crval[1])
    header.update('crpix1', crpix[0])
    header.update('crpix2', crpix[1])
    header.update('cd1_1' , cd[0,0])
    header.update('cd2_1' , cd[1,0])
    header.update('cd1_2' , cd[0,1])
    header.update('cd2_2' , cd[1,1])
    header.update('ctype1', ctype[0])
    header.update('ctype2', ctype[1])
    header.update('cunit1', cunit[0])
    header.update('cunit2', cunit[1])

    return header


#-------------------------------------------------------------------------------


def flatten_sliced_shape(shape):
    if shape is None: return shape
    if _my_isscalar(shape):
        return (int(shape),)
    return tuple(map(np.sum, shape))

   
#-------------------------------------------------------------------------------


def combine_sliced_shape(shape, nsamples):
    if _my_isscalar(shape):
        shape = [ shape ]
    else:
        shape = list(shape) # list makes a shallow copy
    if _my_isscalar(nsamples):
        nsamples = (int(nsamples),)
    else:
        nsamples = tuple(nsamples)
    shape.append(nsamples)
    return tuple(shape)

   
#-------------------------------------------------------------------------------

    
def validate_sliced_shape(shape, nsamples=None):
    # convert shape and nsamples to tuple
    if shape is None:
        if nsamples is None:
            return None
        shape = ()
    elif _my_isscalar(shape):
        shape = (int(shape),)
    else:
        shape = tuple(shape)
    if nsamples is not None:
        if _my_isscalar(nsamples):
            nsamples = (int(nsamples),)
        else:
            nsamples = tuple(nsamples)
    
    if len(shape) == 0:
        if nsamples is not None and len(nsamples) != 0:
            raise ValueError("The input is scalar, but nsamples is equal to '" \
                             + str(nsamples) + "'.")
        return (shape,)
    
    if nsamples is None:
        if _my_isscalar(shape[-1]):
            nsamples = int(shape[-1])
        else:
            nsamples = tuple(map(int, shape[-1]))
    else:
        if len(nsamples) == 0:
            raise ValueError('The input is not scalar and is incompatible wit' \
                             'h nsamples.')
        if np.any(np.array(nsamples) < 0):
            raise ValueError('The input nsamples has negative values.')
        elif np.sum(nsamples) != np.sum(shape[-1]):
            raise ValueError('The sliced input has an incompatible number of ' \
                "samples '" + str(nsamples) + "' instead of '" + str(shape[-1])\
                + "'.")
        if len(nsamples) == 1:
            nsamples = nsamples[0]
    
    l = list(shape[0:-1])
    l.append(nsamples)
    return tuple(l)

def _save_derived_units(filename, du):
    if not du:
        return
    buffer = StringIO.StringIO()
    pickle.dump(du, buffer, pickle.HIGHEST_PROTOCOL)
    data = np.frombuffer(buffer.getvalue(), np.uint8)
    header = create_fitsheader(data, extname='derived_units')
    pyfits.append(filename, data, header)
