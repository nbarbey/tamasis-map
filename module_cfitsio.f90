! interface to some C routines in CFITSIO 3.0
module module_cfitsio

    use, intrinsic :: ISO_C_BINDING
    implicit none

    integer(kind=C_INT), bind(C, name='READONLY')  :: CFITSIO_READONLY
    integer(kind=C_INT), bind(C, name='READWRITE') :: CFITSIO_READWRITE

    interface

        !int fits_open_file( fitsfile **fptr, char *filename, int mode, int *status)
        subroutine fits_open_file(fptr, filename, mode, status) bind(C, name='ffopen')
            import C_CHAR, C_INT, C_PTR
            type(C_PTR), intent(out)               :: fptr
            character(kind=C_CHAR), intent(in)     :: filename(*)
            integer(kind=C_INT), value, intent(in) :: mode
            integer(kind=C_INT), intent(inout)     :: status
        end subroutine fits_open_file

        !int fits_hdr2str(fitsfile *fptr, int nocomments, char **exclist, int nexc, > char **header, int *nkeys, int *status)
        subroutine fits_hdr2str(fptr, nocomments, exclist, nexc, header, nkeys, status) bind(C, name='ffhdr2str')
            import C_INT, C_PTR
            type(C_PTR), value, intent(in)     :: fptr
            integer(kind=C_INT), value         :: nocomments
            type(C_PTR), intent(in)            :: exclist
            integer(kind=C_INT), value         :: nexc
            type(C_PTR), intent(out)           :: header
            integer(kind=C_INT), intent(out)   :: nkeys
            integer(kind=C_INT), intent(inout) :: status
        end subroutine fits_hdr2str

        !int ffclos(fitsfile *fptr, int *status);
        subroutine fits_close_file(fptr, status) bind(C, name='ffclos')
            import C_INT, C_PTR
            type(C_PTR), value, intent(in)     :: fptr
            integer(kind=C_INT), intent(inout) :: status
        end subroutine fits_close_file

        !void ffrprt(FILE *stream, int status);
        subroutine fits_report_error(stream, status) bind(C, name='ffrprt')
            import C_INT, C_PTR
            type(C_PTR), value, intent(in)         :: stream
            integer(kind=C_INT), value, intent(in) :: status
        end subroutine fits_report_error

    end interface

end module module_cfitsio
