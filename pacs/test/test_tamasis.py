import numpy
import pyfits
import os
import tamasis

from tamasis import *
from uuid import uuid1

class TestFailure(Exception): pass

tamasis.__verbose__ = False

data_dir = os.path.dirname(__file__) + '/data/'

# slice[10:19]
obs = PacsObservation(data_dir+'frames_blue.fits[11:20]')
tod = obs.get_tod()

filename = 'obs-'+str(uuid1())+'.fits'
try:
    obs.save(filename, tod)
    obs2 = PacsObservation(filename)
    tod2 = obs2.get_tod(raw=True)
    status2 = obs2.status
finally:
    try:
        os.remove(filename)
    except:
        pass
for field in obs.status.dtype.names:
    status = obs.status[10:20]
    if isinstance(status[field][0], str):
        if numpy.any(status[field] != status2[field]): raise TestFailure('Status problem with: '+field)
    elif not numpy.allclose(status[field], status2[field]): raise TestFailure('Status problem with: '+field)
if not numpy.allclose(tod, tod2): raise TestFailure()
if not numpy.all(tod.mask == tod2.mask): raise TestFailure()

# all observation
obs = PacsObservation(data_dir+'frames_blue.fits')
tod = obs.get_tod()
filename = 'obs-'+str(uuid1())+'.fits'
try:
    obs.save(filename, tod)
    obs2 = PacsObservation(filename)
    tod2 = obs2.get_tod(raw=True)
    status2 = obs2.status
finally:
    try:
        os.remove(filename)
    except:
        pass
for field in obs.status.dtype.names:
    if isinstance(obs.status[field][0], str):
        if numpy.any(obs.status[field] != status2[field]): raise TestFailure('Status problem with: '+field)
    elif not numpy.allclose(obs.status[field], status2[field]): raise TestFailure('Status problem with: '+field)
if not numpy.allclose(tod, tod2): raise TestFailure()
if not numpy.all(tod.mask == tod2.mask): raise TestFailure()

telescope    = Identity('Telescope PSF')
projection   = Projection(obs, resolution=3.2, oversampling=False, npixels_per_sample=6)
multiplexing = CompressionAverage(obs.instrument.fine_sampling_factor, 'Multiplexing')
crosstalk    = Identity('Crosstalk')
compression  = CompressionAverage(obs)
masking      = Masking(tod.mask)

model = masking * crosstalk * multiplexing * projection * telescope
print(model)
model = projection
print(model)

# naive map
tod.unit = 'Jy/arcsec^2'
tod.mask[:] = 0
backmap = model.T(tod)
unity = Tod.ones(tod.shape, nsamples=tod.nsamples)
weights = model.T(unity)
map_naive = backmap / weights

header = projection.header
header2 = header.copy()
header2['NAXIS1'] += 500
header2['CRPIX1'] += 250
projection2 = Projection(obs, header=header2, oversampling=False)
map_naive2 = mapper_naive(tod, projection2, unit='Jy/arcsec^2')
map_naive3 = map_naive2[:,250:header['NAXIS1']+250]
if any_neq(map_naive, map_naive3, 1.e-7): raise TestFailure('mapper_naive, with custom header')

# test compatibility with photproject
tod = obs.get_tod('Jy/arcsec^2', flatfielding=False, subtraction_mean=False)
map_naive4 = mapper_naive(tod, projection, unit='Jy/pixel')
hdu_ref = pyfits.open(data_dir + 'frames_blue_map_hcss_photproject.fits')[1]
map_ref = Map(hdu_ref.data, hdu_ref.header, unit=hdu_ref.header['qtty____']+'/pixel')
std_naive = numpy.std(map_naive4[40:60,40:60])
std_ref = numpy.std(map_ref[40:60,40:60])
relerror = abs(std_naive-std_ref) / std_ref
if relerror > 0.025: raise TestFailure('Tncompatibility with HCSS photproject: ' + str(relerror*100)+'%.')
