MODULES += $(wildcard euclid/module_*.f)
SOURCES += $(wildcard euclid/test_*.f)
EXECS += $(SOURCES:.f=)
FORTRANTESTS += $(wildcard test_*.f)

euclid/module_euclidtrapping = module_math module_precision module_sort

euclid/test_euclidtrapping = euclid/module_euclidtrapping module_precision

.PHONY: euclid
euclid: euclid/test_euclidtrapping