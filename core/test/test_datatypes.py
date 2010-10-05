import numpy
import glob
import os
from tamasis import *
from tamasis.datatypes import validate_sliced_shape
from uuid import uuid1

filename = 'tamasistest-'+str(uuid1())
deftype = get_default_dtype_float()

def test_cleanup():
    files = glob.glob(filename+'*')
    for file in files:
        os.remove(file)

class TestFailure(Exception):
    test_cleanup()

# validate scalars
if validate_sliced_shape((),None) != ((),): raise TestFailure()
if validate_sliced_shape([],None) != ((),): raise TestFailure()
if validate_sliced_shape(numpy.array(()),None) != ((),): raise TestFailure()
if validate_sliced_shape((),()) != ((),): raise TestFailure()
if validate_sliced_shape([],()) != ((),): raise TestFailure()
if validate_sliced_shape(numpy.array(()),()) != ((),): raise TestFailure()

# validate arrays of size 0
if validate_sliced_shape((0,),None) != ((0,),): raise TestFailure()
if validate_sliced_shape((0,),(0,)) != ((0,),): raise TestFailure()
if validate_sliced_shape([0],None) != ((0,),): raise TestFailure()
if validate_sliced_shape([0],(0,)) != ((0,),): raise TestFailure()

# validate arrays with slices of size 0
a = numpy.ones((1,0,1))
if validate_sliced_shape(a.shape, None) != (1,0,(1,)): raise TestFailure()
if validate_sliced_shape(a.shape, 1) != (1,0,(1,)): raise TestFailure()
if validate_sliced_shape(a.shape, (1,)) != (1,0,(1,)): raise TestFailure()
a = numpy.ones((1,1,0))
if validate_sliced_shape(a.shape, None) != (1,1,(0,)): raise TestFailure()
if validate_sliced_shape(a.shape, 0) != (1,1,(0,)): raise TestFailure()
if validate_sliced_shape(a.shape, (0,)) != (1,1,(0,)): raise TestFailure()
a = numpy.ones((1,1,3))

if validate_sliced_shape((10,(10,3)), None) != (10, (10,3)): raise TestFailure()
if validate_sliced_shape((10,13), None) != (10, (13,)): raise TestFailure()

# check errors
try:
    junk = validate_sliced_shape((), 0)
    raise TestFailure()
except ValueError:
    pass
try:
    junk = validate_sliced_shape((0,), ())
    raise TestFailure()
except ValueError:
    pass
try:
    junk = validate_sliced_shape((1,), ())
    raise TestFailure()
except ValueError:
    pass
try:
    junk = validate_sliced_shape((1,), (-1,0,2))
    raise TestFailure()
except ValueError:
    pass
try:
    junk = validate_sliced_shape((2,), (3,4))
    raise TestFailure()
except ValueError:
    pass


tod = Tod((2,))
tod = Tod([2])
tod = Tod(numpy.array([2]))
tod = Tod(2)
tod = Tod(numpy.array(2))
tod = Tod((2,), nsamples=1)
tod = Tod([2], nsamples=1)
tod = Tod(numpy.array([2]), nsamples=1)

a = numpy.ones((10,32))
tod = a.view(Tod)
if tod.nsamples != (32,): raise TestFailure()

tod = Tod.empty((10,(3,5)))
if tod.shape != (10,8): raise TestFailure('Tod.empty1')
tod = Tod.empty((10,(3,5)), nsamples=(3,5))
if tod.shape != (10,8): raise TestFailure('Tod.empty2')
try:
    tod = Tod.empty((10,(3,5)), nsamples=(3,4))
    raise TestFailure()
except ValueError:
    pass
if tod.shape != (10,8): raise TestFailure('Tod.empty3')

tod = Tod.zeros((10,(3,5)))
if tod.shape != (10,8): raise TestFailure('Tod.zeros1')
tod = Tod.zeros((10,(3,5)), nsamples=(3,5))
if tod.shape != (10,8): raise TestFailure('Tod.zeros2')
try:
    tod = Tod.zeros((10,(3,5)), nsamples=(3,4))
    raise TestFailure()
except ValueError:
    pass
if tod.shape != (10,8): raise TestFailure('Tod.zeros3')

tod = Tod.ones((10,(3,5)))
if tod.shape != (10,8): raise TestFailure('Tod.ones1')
tod = Tod.ones((10,(3,5)), nsamples=(3,5))
if tod.shape != (10,8): raise TestFailure('Tod.ones2')
try:
    tod = Tod.ones((10,(3,5)), nsamples=(3,4))
    raise TestFailure()
except ValueError:
    pass
if tod.shape != (10,8): raise TestFailure('Tod.ones3')

tod2 = tod + 1
if tod2.shape != (10,8): raise TestFailure('Addition')
if tod2.nsamples != (3,5): raise TestFailure('Addition2')

a = Tod([10,20])
if a.dtype.type != deftype: raise TestFailure()

a = Tod([10,20], mask=[True,False])
b = Tod(a, copy=True)
if id(a.mask) == id(b.mask): raise TestFailure()

b = Tod(a, copy=False)
if id(a) != id(b): raise TestFailure()

othertype = numpy.float32 if deftype is not numpy.float32 else numpy.float64
b = Tod(a, dtype=othertype, copy=False)
if id(a) == id(b): raise TestFailure()
if id(a.mask) != id(b.mask): raise TestFailure()

header = create_fitsheader(numpy.ones((20,10)))
a = FitsArray([10,20], header=header, unit='m')
b = Tod(a)
if id(a.header) == id(b.header): raise TestFailure()
if id(a.unit) != id(b.unit): raise TestFailure()

b = Tod(a, copy=False)
if id(a.header) != id(b.header): raise TestFailure()
if id(a.unit) != id(b.unit): raise TestFailure()

a = Tod([20,10], header=header, unit='m')
b =  FitsArray(a)
if id(a.header) == id(b.header): raise TestFailure()
if id(a.unit) != id(b.unit): raise TestFailure()

b = FitsArray(a, copy=False)
if id(a.header) != id(b.header): raise TestFailure()
if id(a.unit) != id(b.unit): raise TestFailure()

b = FitsArray(a, subok=True)
if id(a) == id(b): raise TestFailure()
if id(a.header) == id(b.header): raise TestFailure()
if id(a.unit) != id(b.unit): raise TestFailure()

b = FitsArray(a, copy=False, subok=True)
if id(a) != id(b): raise TestFailure()

a = Tod([])
if a.shape != (0,): raise TestFailure()
if a.size != 0: raise TestFailure()

a = Tod([], nsamples = (0,))
if a.shape != (0,): raise TestFailure()
if a.size != 0: raise TestFailure()

a = Tod(1)
if a.shape != (): raise TestFailure()
if a.size != 1: raise TestFailure()

a = Tod(1, nsamples = ())
if a.shape != (): raise TestFailure()
if a.size != 1: raise TestFailure()

a = Tod.ones((10,20), nsamples=(5,15))
b = a[:,:12]
if b.nsamples != (12,): raise TestFailure()
b = a[:3,:]
if b.nsamples != a.nsamples: raise TestFailure()
b = a[3]
if b.nsamples != a.nsamples: raise TestFailure()
b = a[3,:]
if b.nsamples != a.nsamples: raise TestFailure()
b = a[:,2]
if not isinstance(b, FitsArray): raise TestFailure()
b = a[4,2]
if not isinstance(b, deftype): raise TestFailure()

m = numpy.ndarray((10,2,10), dtype='int8')
m.flat = numpy.random.random(m.size)*2
a = Tod(numpy.random.random_sample((10,2,10)), mask=m, nsamples=(2,8), unit='Jy')
a.writefits(filename+'_tod.fits')
b = Tod(filename+'_tod.fits')
if numpy.any(a != b) or numpy.any(a.mask != b.mask) or a.nsamples != b.nsamples: raise TestFailure()

test_cleanup()
print 'OK.'
