# Makefile for project TAMASIS
# Author: P. Chanial

FC=ifort
FFLAGS_DEBUG = -g -fast -warn all -openmp
FFLAGS_RELEASE = -fast -openmp -ftz -ip  -ipo -march=native 
LDFLAGS  = -liomp5 $(shell pkg-config --libs cfitsio) $(shell pkg-config --libs wcslib)
FCOMPILER = intelem

FC=gfortran
FFLAGS_DEBUG = -g -O3 -fcheck=all -fopenmp -Wall -fPIC
FFLAGS_RELEASE = -O3 -fopenmp -fPIC
LDFLAGS  = -lgomp $(shell pkg-config --libs cfitsio) $(shell pkg-config --libs wcslib)
FCOMPILER=gnu95

INCLUDES = wcslib-4.4.4-Fortran90
FFLAGS   = $(FFLAGS_RELEASE)

MODULES = precision.f90 string.f90 $(wildcard module_*.f90)
SOURCES = $(wildcard test_*.f90)
EXECS = $(SOURCES:.f90=)

# apply a function for each element of a list
map = $(foreach a,$(2),$(call $(1),$(a)))

# recursively find dependencies
finddeps = $(1).o $(if $($(1)),$(call map,finddeps,$($(1))))

# define module dependencies
module_cfitsio = module_stdio
module_fitstools = string module_cfitsio
module_instrument = precision string
module_pacsinstrument = string module_fitstools module_pacspointing module_pointingmatrix module_projection module_wcs 
module_pacspointing = precision module_fitstools
module_pointingmatrix = module_pointingelement
module_projection = precision module_sort module_stack
module_wcs = module_fitstools module_wcslib string

# define executable dependencies
test_cfitsio = module_cfitsio
test_fitstools = module_fitstools
test_ngc6946_bpj = module_fitstools module_pacsinstrument module_pacspointing module_pointingmatrix module_preprocessor module_projection precision
test_pacs = module_pacsinstrument module_pacspointing module_fitstools
test_pointing = module_pacspointing
test_projection = module_projection module_sort
test_read_config = module_instrument
test_sort = module_sort
test_stack = module_stack
test_stdio = module_stdio module_cfitsio
test_wcs = module_wcs module_fitstools precision
test_wcslib1 = module_wcslib module_cfitsio 
test_wcslib2 = module_wcslib module_fitstools precision
test_wcslibc = module_wcslibc module_cfitsio

.PHONY : all tests
all : $(EXECS) tamasisfortran.so

# if %.mod doesn't exist, make %.o. It will create %.mod with the same 
# timestamp. If it does, do nothing
%.mod : %.o
	@if [ ! -f $@ ]; then \
	    rm $< ;\
	    $(MAKE) $< ;\
	fi

%.o : %.f90
	$(FC) $(FFLAGS) -I$(INCLUDES) -c -o $@ $<

%: %.o
	$(FC) -o $@ $^ $(LDFLAGS)

.SECONDEXPANSION:
$(MODULES:.f90=.o) $(SOURCES:.f90=.o):%.o: $$(addsuffix .mod,$$($$*))
$(EXECS):%:$$(sort $$(call finddeps,$$*))

tamasisfortran.so: tamasisfortran.f90 $(MODULES:.f90=.o)
	unset LDFLAGS ; \
	f2py --fcompiler=${FCOMPILER} --f90exec=$(FC) --f90flags="$(FFLAGS)" -DF2PY_REPORT_ON_ARRAY_COPY=1 -c $^ -m tamasisfortran $(LDFLAGS)

clean:
	rm -f *.o *.mod *.so $(EXECS)

tests:
	@for test in $(EXECS); do \
	echo;\
	echo "Running test: "$$test"...";\
	echo "=============";\
	./$$test; \
	done
