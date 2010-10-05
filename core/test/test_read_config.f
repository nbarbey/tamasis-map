program test_read_config
 
 use module_instrument
 implicit none
 
 type(receiver) :: pacs

 pacs = read_instrument_configfile('/home/pchanial/work/tamasis/example_geometry.txt')

 call write_configuration(pacs)

 ! deallocate the instrument heap variables
 if (allocated(pacs%id))     deallocate(pacs%id)
 if (allocated(pacs%vertex)) deallocate(pacs%vertex)
 if (allocated(pacs%flag))   deallocate(pacs%flag)

 stop 'OK.'

end program test_read_config