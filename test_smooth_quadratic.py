#!/usr/bin/env python2.6
from   matplotlib.pyplot import clim, figure, plot, show, ioff
from   tamasis import *
import os

do_plot = True
ioff()

datadir = os.getenv('PACS_DATA')+'/transpScan/'
pacs = PacsObservation(filename=[datadir+'1342184598_blue_PreparedFrames.fits',
                                 datadir+'1342184599_blue_PreparedFrames.fits'],
                       resolution=3.2,
                       fine_sampling_factor=1,
                       keep_bad_detectors=False)

telescope    = Identity('Telescope PSF')
projection   = Projection(pacs, npixels_per_sample=5)
multiplexing = CompressionAverage(1, 'Multiplexing')
crosstalk    = Identity('Crosstalk')
compression  = CompressionAverage(4)

model = compression * crosstalk * multiplexing * projection * telescope

# read the Tod off the disk
tod40Hz = pacs.get_tod()

# remove drift
x = numpy.arange(tod40Hz.shape[1])
slope = scipy.polyfit(x, tod40Hz.T, deg=6)
drift = tod40Hz.copy()
for i in xrange(tod40Hz.shape[0]):
    drift[i,:] = scipy.polyval(slope[:,i], x)

idetector=5
if do_plot:
    figure()
    plot(tod40Hz[idetector,:])
    plot(drift[idetector,:],'r')
    show()

tod40Hz -= drift

tod40Hz = filter_median(tod40Hz, 10000)

mask_before = tod40Hz.mask.copy('a')

# second level deglitching
tod40Hz.mask = deglitch_l2mad(tod40Hz, projection)

if do_plot:
    figure()
    plot(tod40Hz[idetector,:])
    index=numpy.where(tod40Hz.mask[idetector,:])
    plot(index,tod40Hz[idetector,index],'ro')
    show()

masking   = Masking(tod40Hz.mask)
model40Hz = masking * projection
map_naive40Hz = naive_mapper(tod40Hz, model40Hz)

if do_plot:
    map_naive40Hz.imshow()
    clim(-0.00002,0.00002)

# compressed TOD
tod = compression.direct(tod40Hz).copy()
print tod

# naive map
map_naive = naive_mapper(tod, model)
