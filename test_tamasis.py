from tamasis import *
import numpy

pacs = PacsObservation(filename=tamasis_dir+'tests/frames_blue.fits',
                       resolution=3.2,
                       fine_sampling_factor=1, 
                       keep_bad_detectors=False)

tod = pacs.get_tod()

telescope    = Identity('Telescope PSF')
projection   = Projection(pacs, finer_sampling=False, npixels_per_sample=6)
multiplexing = CompressionAverage(pacs.fine_sampling_factor, 'Multiplexing')
crosstalk    = Identity('Crosstalk')
compression  = CompressionAverage(pacs.compression_factor)
masking      = Masking(tod.mask)

model = masking * crosstalk * multiplexing * projection * telescope
model = projection
print model

# naive map
backmap = model.transpose(tod)
tod[:] = 1
weights = model.transpose(tod)
map_naive = backmap / weights

print 'OK.'

#ra0  = 20.
#dec0 = 0.1
#time = numpy.arange(0.,100., 1./40)
#simulation = PacsSimulation(inputmap           = 
#                            time               = time \
#                            ra                 = numpy.linspace(ra0, ra0+0.1, nsamples)   \
#                            dec                = numpy.linspace(dec0, dec0+0.1, nsamples) \
#                            pa                 = numpy.zeros(nsamples) \
#                            chop               = numpy.zeros(nsamples) \
#                            array              = 'blue'        \
#                            npixelsPerSample   = 9             \
#                            observingMode      = 'transparent' \
#                            fineSamplingFactor = 1             \
#                            compressionFactor  = 1             \
#                            keepBadDetectors   = True)

