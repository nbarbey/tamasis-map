! Tamasis interface for f2py
!
! Author: P. Chanial

subroutine pacs_info_instrument_init(filename, nfilenames, band, transparent_mode, status)

    use iso_fortran_env,        only : ERROR_UNIT
    use module_fitstools,       only : FLEN_VALUE, ft_close, ft_open, ft_read_keyword, ft_read_keyword_hcss
    use module_pacsobservation, only : PacsObservationSlice
    implicit none

    !f2py threadsafe
    !f2py intent(in)              :: filename
    !f2py intent(in)              :: nfilenames
    !f2py intent(out)             :: band
    !f2py intent(out)             :: status

    character(len=*), intent(in)  :: filename
    integer, intent(in)           :: nfilenames
    character(len=7), intent(out) :: band
    logical, intent(out)          :: transparent_mode
    integer, intent(out)          :: status

    class(PacsObservationSlice), allocatable :: slice
    integer                                  :: iobs, unit, first, last
    character(len=FLEN_VALUE)                :: camname, blue, compmode
    character(len=7)                         :: band_
    logical                                  :: found

    ! split input filename
    if (mod(len(filename), nfilenames) /= 0) then
        stop 'PACS_INFO_INIT: Invalid filename length.'
    end if

    band = 'unknown'
    transparent_mode = .true.
    allocate (slice)

    do iobs = 1, nfilenames

        call slice%set_filename(filename((iobs-1)*len(filename)/nfilenames+1:iobs*len(filename)/nfilenames), first, last, status)
        if (status /= 0) return

        call ft_open(trim(slice%filename), unit, status)
        if (status /= 0) return

        call ft_read_keyword_hcss(unit, 'camName', camname, status=status)
        if (status /= 0) return

        call ft_read_keyword_hcss(unit, 'blue', blue, found, status)
        if (status /= 0) return
        if (.not. found) then
            call ft_read_keyword(unit, 'FILTER', blue, status=status)
            if (status /= 0) return
        end if

        call ft_read_keyword_hcss(unit, 'compMode', compmode, status=status)
        if (status /= 0) return

        call ft_close(unit, status)
        if (status /= 0) return

        if (camname == 'Blue Photometer') then
            if (blue == 'blue1' .or. blue == 'blue70um') then
                band_ = 'blue'
            else if (blue == 'blue2' .or. blue == 'blue100um') then
                band_ = 'green'
            else
                write (ERROR_UNIT, '(a)') "Error: Invalid blue camera identifier '" // trim(blue) // "' in file '" //              &
                      trim(slice%filename) // "'."
                status = 1
                return
            end if
        else if (camname == 'Red Photometer') then
            band_ = 'red'
        else
            write (ERROR_UNIT, '(a)') "Error: Invalid camera name '" // trim(camname) // "' in file '" // trim(slice%filename)     &
                  // "'."
            status = 1
            return
        end if

        if (iobs == 1) then
            band = band_
        else if (band_ /= band) then
            write (ERROR_UNIT, '(a)') "Error: Observations are not performed with the same band."
            status = 1
            return
        end if

        if (compmode /= 'Photometry Lossless Compression Mode') then
            transparent_mode = .false.
        end if

    end do

end subroutine pacs_info_instrument_init


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_info_instrument(band, nrows, ncolumns, input_active_fraction, detector_bad, detector_center,        &
                                detector_corner, detector_area, distortion_yz, flatfield_optical, flatfield_detector, responsivity,&
                                output_active_fraction, status)

    use module_pacsinstrument, only : read_calibration_files
    use module_tamasis,        only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)             :: band
    !f2py intent(in)             :: nrows
    !f2py intent(in)             :: ncolumns
    !f2py intent(in)             :: input_active_fraction
    !f2py intent(out)            :: detector_bad
    !f2py intent(out)            :: detector_center
    !f2py intent(out)            :: detector_corner
    !f2py intent(out)            :: detector_area
    !f2py intent(out)            :: distortion_yz
    !f2py intent(out)            :: flatfield_optical
    !f2py intent(out)            :: flatfield_detector
    !f2py intent(out)            :: responsivity
    !f2py intent(out)            :: output_active_fraction
    !f2py intent(out)            :: status

    character(len=*), intent(in) :: band
    integer, intent(in)          :: nrows, ncolumns
    real(p), intent(in)          :: input_active_fraction
    logical*1, intent(out)       :: detector_bad(nrows,ncolumns)
    real(p), intent(out)         :: detector_center(2,nrows,ncolumns)
    real(p), intent(out)         :: detector_corner(2,4,nrows,ncolumns)
    real(p), intent(out)         :: detector_area(nrows,ncolumns)
    real(p), intent(out)         :: distortion_yz(2,3,3,3)
    real(p), intent(out)         :: flatfield_optical(nrows,ncolumns)
    real(p), intent(out)         :: flatfield_detector(nrows,ncolumns)
    real(p), intent(out)         :: responsivity
    real(p), intent(out)         :: output_active_fraction
    integer, intent(out)         :: status

    logical*1, allocatable :: detector_bad_all(:,:)
    real(p), allocatable   :: detector_center_all(:,:,:)
    real(p), allocatable   :: detector_corner_all(:,:,:,:)
    real(p), allocatable   :: detector_area_all(:,:)
    real(p), allocatable   :: flatfield_optical_all(:,:)
    real(p), allocatable   :: flatfield_detector_all(:,:)

    ! read calibration files
    output_active_fraction = input_active_fraction
    call read_calibration_files(band, detector_bad_all, detector_center_all, detector_corner_all, detector_area_all,               &
         flatfield_optical_all, flatfield_detector_all, distortion_yz, responsivity, output_active_fraction, status)
    if (status /= 0) return

    ! copy the allocatable arrays
    detector_bad       = detector_bad_all
    detector_center    = detector_center_all
    detector_corner    = detector_corner_all
    detector_area      = detector_area_all
    flatfield_optical  = flatfield_optical_all
    flatfield_detector = flatfield_detector_all

end subroutine pacs_info_instrument


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_info_observation_init(filename, nfilenames, nsamples, status)

    use module_fitstools,       only : ft_close, ft_open, ft_read_keyword
    use module_pacsobservation, only : PacsObservationSlice
    use module_tamasis,         only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)             :: filename
    !f2py intent(in)             :: nfilenames
    !f2py intent(out)            :: nsamples(nfilenames)
    !f2py intent(out)            :: status

    character(len=*), intent(in) :: filename
    integer, intent(in)          :: nfilenames
    integer, intent(out)         :: nsamples(nfilenames)
    integer, intent(out)         :: status

    class(PacsObservationSlice), allocatable :: slice
    integer                                  :: iobs, unit, first, last
    allocate (slice)

    do iobs = 1, nfilenames

        call slice%set_filename(filename((iobs-1)*len(filename)/nfilenames+1:iobs*len(filename)/nfilenames), first, last, status)
        if (status /= 0) return

        call ft_open(trim(slice%filename) // '[Signal]', unit, status)
        if (status /= 0) return

        call ft_read_keyword(unit, 'NAXIS1', nsamples(iobs), status=status)
        if (status /= 0) return

        call ft_close(unit, status)
        if (status /= 0) return

    end do

end subroutine pacs_info_observation_init


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_info_observation(filename, nfilenames, policy, nsamples_tot, obsid, cusmode, compression, unit, ra, dec, cam_angle,&
                                 scan_angle, scan_length, scan_step, scan_nlegs, frame_time, frame_ra, frame_dec,      &
                                 frame_pa, frame_chop, frame_info, frame_masked, frame_removed, nmasks, mask_name, mask_activated, &
                                 status)

    use module_observation,     only : POINTING_INSCAN, POINTING_TURNAROUND, POINTING_OTHER, MaskPolicy
    use module_pacsobservation, only : PacsObservation
    use module_tamasis,         only : POLICY_KEEP, POLICY_MASK, POLICY_REMOVE, p
    implicit none

    !f2py threadsafe
    !f2py intent(in)            :: filename
    !f2py intent(in)            :: nfilenames
    !f2py intent(in)            :: policy
    !f2py intent(in)            :: nsamples_tot
    !f2py character(len=70*nfilenames), intent(out), depend(nfilenames) :: cusmode, unit
    !f2py intent(out)           :: obsid, compression, ra, dec, cam_angle, scan_angle, scan_length, scan_step
    !f2py intent(out)           :: scan_nlegs
    !f2py intent(out)           :: frame_time, frame_ra, frame_dec, frame_pa, frame_chop, frame_info, frame_masked, frame_removed
    !f2py intent(out)           :: nmasks, mask_activated
    !f2py character(len=70*32*nfilenames), intent(out), depend(nfilenames) :: mask_name
    !f2py intent(out)           :: status

    character(len=*), intent(in)                    :: filename
    integer, intent(in)                             :: nfilenames
    integer, intent(in)                             :: policy(4)
    integer, intent(in)                             :: nsamples_tot
    character(len=70*nfilenames), intent(out)       :: cusmode, unit !XXX hack around f2py bug with array of characters
    real(p), intent(out), dimension(nfilenames)     :: ra, dec, cam_angle, scan_angle, scan_length, scan_step
    integer, intent(out), dimension(nfilenames)     :: obsid, compression, scan_nlegs, nmasks
    real(p), intent(out), dimension(nsamples_tot)   :: frame_time, frame_ra, frame_dec, frame_pa, frame_chop, frame_info
    logical*1, intent(out), dimension(nsamples_tot) :: frame_masked, frame_removed
    character(len=70*32*nfilenames), intent(out)    :: mask_name
    logical*1, dimension(32,nfilenames)             :: mask_activated
    integer, intent(out)                            :: status

    integer, parameter                  :: NMASKS_MAX = 32
    integer, parameter                  :: FLEN_VALUE = 70
    class(PacsObservation), allocatable :: obs
    type(MaskPolicy)                    :: mask_policy
    integer                             :: iobs, isample, imask, nsamples, dest
    character(len=len(filename)/nfilenames), allocatable :: filename_(:)

    ! split input filename
    if (mod(len(filename), nfilenames) /= 0) then
        stop 'PACS_INFO: Invalid filename length.'
    end if
    allocate(filename_(nfilenames))
    do iobs = 1, nfilenames
        filename_(iobs) = filename((iobs-1)*len(filename_)+1:iobs*len(filename_))
    end do

    ! initialise policy
    mask_policy = MaskPolicy(inscan=policy(1), turnaround=policy(2), other=policy(3), invalid=policy(4))

    ! read observations
    allocate (obs)
    call obs%init(filename_, mask_policy, status, verbose=.true.)
    if (status /= 0) return

    cusmode = ''
    unit = ''
    mask_name = ''
    mask_activated = .false.
    do iobs = 1, nfilenames
        cusmode((iobs-1)*FLEN_VALUE+1:iobs*FLEN_VALUE) = obs%slice(iobs)%observing_mode
        unit   ((iobs-1)*FLEN_VALUE+1:iobs*FLEN_VALUE) = obs%slice(iobs)%unit
        nmasks(iobs) = obs%slice(iobs)%nmasks
        do imask = 1, nmasks(iobs)
            dest = ((iobs-1)*NMASKS_MAX+(imask-1))*FLEN_VALUE
            mask_name(dest+1:dest+FLEN_VALUE) = obs%slice(iobs)%mask_name(imask)
            mask_activated(imask,iobs) = obs%slice(iobs)%mask_activated(imask)
        end do
    end do
    obsid       = obs%slice%obsid
    compression = obs%slice%compression_factor
    ra          = obs%slice%ra
    dec         = obs%slice%dec
    cam_angle   = obs%slice%cam_angle
    scan_angle  = obs%slice%scan_angle
    scan_length = obs%slice%scan_length
    scan_step   = obs%slice%scan_step
    scan_nlegs  = obs%slice%scan_nlegs
    
    dest = 1
    do iobs = 1, obs%nslices
        nsamples = obs%slice(iobs)%nsamples
        frame_time   (dest:dest+nsamples-1) = obs%slice(iobs)%p%time
        frame_ra     (dest:dest+nsamples-1) = obs%slice(iobs)%p%ra
        frame_dec    (dest:dest+nsamples-1) = obs%slice(iobs)%p%dec
        frame_pa     (dest:dest+nsamples-1) = obs%slice(iobs)%p%pa
        frame_chop   (dest:dest+nsamples-1) = obs%slice(iobs)%p%chop
        frame_masked (dest:dest+nsamples-1) = obs%slice(iobs)%p%masked
        frame_removed(dest:dest+nsamples-1) = obs%slice(iobs)%p%removed
        do isample = 1, nsamples
            if (obs%slice(iobs)%p(isample)%inscan) then
                frame_info(dest) = POINTING_INSCAN
            else if (obs%slice(iobs)%p(isample)%turnaround) then
                frame_info(dest) = POINTING_TURNAROUND
            else
                frame_info(dest) = POINTING_OTHER
            end if
            dest = dest + 1
        end do
    end do

end subroutine pacs_info_observation


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_read_filter_calibration_ncorrelations(band, ncorrelations, status)

    use module_pacsinstrument, only : read_filter_calibration_ncorrelations
    implicit none

    !f2py intent(in)             :: band
    !f2py intent(out)            :: ncorrelations
    !f2py intent(out)            :: status
    
    character(len=*), intent(in) :: band
    integer, intent(out)         :: ncorrelations
    integer, intent(out)         :: status
    
    ncorrelations = read_filter_calibration_ncorrelations(band, status)

end subroutine pacs_read_filter_calibration_ncorrelations


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_read_filter_calibration(band, ncorrelations, ndetectors, mask, nrows, ncolumns, data, status)

    use iso_fortran_env,       only : ERROR_UNIT
    use module_filtering,      only : FilterUncorrelated
    use module_pacsinstrument, only : read_filter_calibration
    use module_tamasis,        only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)             :: band
    !f2py intent(in)             :: ncorrelations
    !f2py intent(in)             :: ndetectors
    !f2py intent(in)             :: mask
    !f2py intent(hide)           :: nrows = shape(mask,0)
    !f2py intent(hide)           :: ncolumns = shape(mask,1)
    !f2py intent(out)            :: data
    !f2py intent(out)            :: status

    character(len=*), intent(in) :: band
    integer, intent(in)          :: ncorrelations
    integer, intent(in)          :: ndetectors
    logical*1, intent(in)        :: mask(nrows,ncolumns)
    integer, intent(in)          :: nrows
    integer, intent(in)          :: ncolumns
    real(p), intent(out)         :: data(ncorrelations+1,ndetectors)
    integer, intent(out)         :: status

    type(FilterUncorrelated)     :: filter

    call read_filter_calibration(band, mask, filter, status)
    if (status /= 0) return

    if (filter%ndetectors /= ndetectors) then
        status = 1
        write (ERROR_UNIT,'(a,2(i0,a))') "The specified number of detectors '", ndetectors, "' does not match that in the calibrati&
              &on file '", filter%ndetectors, "'."
    end if
    if (filter%ncorrelations /= ncorrelations) then
        status = 1
        write (ERROR_UNIT,'(a,2(i0,a))') "The specified number of correlations '", ncorrelations, "' does not match that in the cal&
              &ibration file '", filter%ncorrelations, "'."
    end if
    if (status /= 0) return

    data = filter%data

end subroutine pacs_read_filter_calibration


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_map_header(band, nslices, npointings, nsamples_tot, compression_factor, delay, fine_sampling_factor,               &
                           oversampling, time, ra, dec, pa, chop, masked, removed, detector_mask, nrows, ncolumns, detector_bad,   &
                           detector_corner, distortion_yz, resolution, header, status)

    use module_pacsinstrument,  only : PacsInstrument
    use module_pacsobservation, only : PacsObservation
    use module_tamasis,         only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)                               :: band
    !f2py intent(hide),                            :: nslices=size(npointings)
    !f2py intent(in)                               :: npointings(nslices)
    !f2py intent(hide),                            :: nsamples_tot = size(time)
    !f2py intent(in)                               :: compression_factor(nslices)
    !f2py intent(in)                               :: delay(nslices)
    !f2py intent(in)                               :: fine_sampling_factor
    !f2py intent(in)                               :: oversampling
    !f2py intent(in)                               :: time(nsamples_tot)
    !f2py intent(in)                               :: ra(nsamples_tot)
    !f2py intent(in)                               :: dec(nsamples_tot)
    !f2py intent(in)                               :: pa(nsamples_tot)
    !f2py intent(in)                               :: chop(nsamples_tot)
    !f2py intent(in)                               :: masked(nsamples_tot)
    !f2py intent(in)                               :: removed(nsamples_tot)
    !f2py intent(in)                               :: detector_mask(nrows,ncolumns)
    !f2py intent(hide)                             :: nrows = shape(detector_mask,0)
    !f2py intent(hide)                             :: ncolumns = shape(detector_mask,1)
    !f2py intent(in)                               :: detector_bad(nrows,ncolumns)
    !f2py intent(in)                               :: detector_corner(2,4,nrows,ncolumns)
    !f2py intent(in)                               :: distortion_yz(2,3,3,3)
    !f2py intent(in)                               :: resolution
    !f2py intent(out)                              :: header
    !f2py intent(out)                              :: status

    character(len=*), intent(in)                   :: band
    integer, intent(in)                            :: nslices
    integer, intent(in)                            :: npointings(nslices)
    integer*8, intent(in)                          :: nsamples_tot
    integer, intent(in)                            :: compression_factor(nslices)
    real(p), intent(in)                            :: delay(nslices)
    integer, intent(in)                            :: fine_sampling_factor
    logical, intent(in)                            :: oversampling
    real(p), intent(in), dimension(nsamples_tot)   :: time, ra, dec, pa, chop
    logical*1, intent(in), dimension(nsamples_tot) :: masked, removed
    logical*1, intent(in)                          :: detector_mask(nrows,ncolumns)
    integer, intent(in)                            :: nrows
    integer, intent(in)                            :: ncolumns
    logical*1, intent(in)                          :: detector_bad(nrows,ncolumns)
    real(p), intent(in)                            :: detector_corner(2,4,nrows,ncolumns)
    real(p), intent(in)                            :: distortion_yz(2,3,3,3)
    real(p), intent(in)                            :: resolution
    character(len=2880), intent(out)               :: header
    integer, intent(out)                           :: status

    class(PacsObservation), allocatable :: obs
    class(PacsInstrument), allocatable  :: pacs

    ! initialise observations
    allocate(obs)
    call obs%init_with_variables(time, ra, dec, pa, chop, masked, removed, npointings, compression_factor, delay, status)
    if (status /= 0) return

    ! initialise pacs instrument
    allocate (pacs)
    call pacs%init_with_variables(band, detector_mask, fine_sampling_factor, status, detector_bad_all=detector_bad,                &
                                  detector_corner_all=detector_corner, distortion_yz=distortion_yz)
    if (status /= 0) return

    ! compute the map header
    call pacs%compute_map_header(obs, oversampling, resolution, header, status)

end subroutine pacs_map_header


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_tod(band, filename, nslices, npointings, nsamples_tot, compression_factor, delay, fine_sampling_factor, time, ra,  &
                    dec, pa, chop, masked, removed, detector_mask, detector_bad, flatfield_detector, do_flatfielding,              &
                    do_subtraction_mean, nvalids, ndetectors, selected_mask, nrows, ncolumns, signal, mask, status)


    use iso_fortran_env,        only : ERROR_UNIT
    use module_pacsinstrument,  only : PacsInstrument
    use module_pacsobservation, only : PacsObservation
    use module_preprocessor,    only : divide_vectordim2, remove_nan, subtract_meandim1
    use module_tamasis,         only : p
    use module_string,          only : strsplit
    implicit none

    !f2py threadsafe
    !f2py intent(in)                               :: band
    !f2py intent(in)                               :: filename
    !f2py intent(hide)                             :: nslices=size(npointings)
    !f2py intent(in)                               :: npointings(nslices)
    !f2py intent(hide)                             :: nsamples_tot = size(time)
    !f2py intent(in)                               :: compression_factor(nslices)
    !f2py intent(in)                               :: delay(nslices)
    !f2py intent(in)                               :: fine_sampling_factor
    !f2py intent(in)                               :: time(nsamples_tot)
    !f2py intent(in)                               :: ra(nsamples_tot)
    !f2py intent(in)                               :: dec(nsamples_tot)
    !f2py intent(in)                               :: pa(nsamples_tot)
    !f2py intent(in)                               :: chop(nsamples_tot)
    !f2py intent(in)                               :: masked(nsamples_tot)
    !f2py intent(in)                               :: removed(nsamples_tot)
    !f2py intent(in)                               :: detector_mask(nrows,ncolumns)
    !f2py intent(in)                               :: detector_bad(nrows,ncolumns)
    !f2py intent(in)                               :: flatfield_detector(nrows,ncolumns)
    !f2py intent(in)                               :: do_flatfielding
    !f2py intent(in)                               :: do_subtraction_mean
    !f2py intent(in)                               :: nvalids
    !f2py intent(in)                               :: ndetectors
    !f2py intent(in)                               :: selected_mask
    !f2py intent(hide)                             :: nrows=shape(detector_mask,0)
    !f2py intent(hide)                             :: ncolumns=shape(detector_mask,1)
    !f2py intent(out)                              :: signal(nvalids,ndetectors)
    !f2py intent(out)                              :: mask(nvalids,ndetectors)
    !f2py intent(out)                              :: status

    character(len=*), intent(in)                   :: band
    character(len=*), intent(in)                   :: filename
    integer, intent(in)                            :: nslices
    integer, intent(in)                            :: npointings(nslices)
    integer*8, intent(in)                          :: nsamples_tot
    integer, intent(in)                            :: compression_factor(nslices)
    real(p), intent(in)                            :: delay(nslices)
    integer, intent(in)                            :: fine_sampling_factor
    real(p), intent(in), dimension(nsamples_tot)   :: time, ra, dec, pa, chop
    logical*1, intent(in), dimension(nsamples_tot) :: masked, removed
    logical*1, intent(in)                          :: detector_mask(nrows,ncolumns)
    logical*1, intent(in)                          :: detector_bad(nrows,ncolumns)
    real(p), intent(in)                            :: flatfield_detector(nrows,ncolumns)
    logical, intent(in)                            :: do_flatfielding, do_subtraction_mean
    integer, intent(in)                            :: nvalids
    integer, intent(in)                            :: ndetectors
    integer, intent(in)                            :: nrows
    integer, intent(in)                            :: ncolumns
    character(len=*), intent(in)                   :: selected_mask
    real(p), intent(out)                           :: signal(nvalids, ndetectors)
    logical*1, intent(out)                         :: mask(nvalids, ndetectors)
    integer, intent(out)                           :: status

    class(PacsObservation), allocatable            :: obs
    class(PacsInstrument), allocatable             :: pacs
    integer                                        :: iobs, destination, filename_len
    character(len=len(selected_mask)), allocatable :: selected_mask_(:)

    ! initialise observations
    allocate(obs)
    call obs%init_with_variables(time, ra, dec, pa, chop, masked, removed, npointings, compression_factor, delay, status)
    if (status /= 0) return

    ! split input filename
    if (mod(len(filename), nslices) /= 0) then
        stop 'PACS_TOD: Invalid filename length.'
    end if
    filename_len = len(filename) / nslices
    do iobs = 1, nslices
        obs%slice(iobs)%filename = filename((iobs-1)*filename_len+1:iobs*filename_len)
    end do

    ! initialise pacs instrument
    allocate (pacs)
    call pacs%init_with_variables(band, detector_mask, fine_sampling_factor, status, detector_bad_all=detector_bad,                &
                                  flatfield_detector_all=flatfield_detector)
    if (status /= 0) return

    ! check number of detectors
    if (pacs%ndetectors /= ndetectors) then
        status = 1
        write (ERROR_UNIT,'(a,2(i0,a))') "The specified number of detectors '", ndetectors, "' is incompatible with that from the i&
              &nput detector mask '", pacs%ndetectors, "'."
        return
    end if

    ! split masks
    call strsplit(selected_mask, ',', selected_mask_)

    ! read timeline
    call pacs%read(obs, selected_mask_, signal, mask, status, verbose=.true.)
    if (status /= 0) return

    ! detector flat fielding
    if (do_flatfielding) then
        call divide_vectordim2(signal, pacs%flatfield_detector)
    end if

    ! subtract the mean of each detector timeline
    if (do_subtraction_mean) then
        destination = 1
        do iobs=1, nslices
            call subtract_meandim1(signal(destination:destination+obs%slice(iobs)%nvalids-1,:),                                    &
                                   mask(destination:destination+obs%slice(iobs)%nvalids-1,:))
            destination = destination + obs%slice(iobs)%nvalids
        end do
    end if

    ! remove NaN
    call remove_nan(signal, mask)
    
end subroutine pacs_tod


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_pointing_matrix(band, nslices, nvalids, npointings, nsamples_tot, compression_factor, delay, fine_sampling_factor, &
                                oversampling, time, ra, dec, pa, chop, masked, removed, method, detector_mask, nrows, ncolumns,    &
                                ndetectors, detector_center, detector_corner, detector_area, distortion_yz, npixels_per_sample,    &
                                header, pmatrix, new_npixels_per_sample, status)

    use iso_fortran_env,        only : ERROR_UNIT
    use module_fitstools,       only : ft_read_keyword
    use module_pacsinstrument,  only : PacsInstrument, NDIMS, NVERTICES, NEAREST_NEIGHBOUR, SHARP_EDGES
    use module_pacsobservation, only : PacsObservation, MaskPolicy
    use module_pointingmatrix,  only : PointingElement
    use module_tamasis,         only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)                               :: band
    !f2py intent(hide),                            :: nslices=size(npointings)
    !f2py intent(in)                               :: nvalids
    !f2py intent(in)                               :: npointings(nslices)
    !f2py intent(hide),                            :: nsamples_tot = size(time)
    !f2py intent(in)                               :: compression_factor(nslices)
    !f2py intent(in)                               :: delay(nslices)
    !f2py intent(in)                               :: fine_sampling_factor
    !f2py intent(in)                               :: oversampling
    !f2py intent(in)                               :: time(nsamples_tot)
    !f2py intent(in)                               :: ra(nsamples_tot)
    !f2py intent(in)                               :: dec(nsamples_tot)
    !f2py intent(in)                               :: pa(nsamples_tot)
    !f2py intent(in)                               :: chop(nsamples_tot)
    !f2py intent(in)                               :: masked(nsamples_tot)
    !f2py intent(in)                               :: removed(nsamples_tot)
    !f2py intent(in)                               :: method
    !f2py intent(in)                               :: detector_mask(nrows,ncolumns)
    !f2py intent(hide)                             :: nrows = shape(detector_mask,0)
    !f2py intent(hide)                             :: ncolumns = shape(detector_mask,1)
    !f2py intent(in)                               :: ndetectors
    !f2py intent(in)                               :: detector_center(2,nrows,ncolumns)
    !f2py intent(in)                               :: detector_corner(2,4,nrows,ncolumns)
    !f2py intent(in)                               :: detector_area(nrows,ncolumns)
    !f2py intent(in)                               :: distortion_yz(2,3,3,3)
    !f2py intent(in)                               :: npixels_per_sample
    !f2py intent(in)                               :: header
    !f2py integer*8, intent(inout),depend(npixels_per_sample,nvalids,ndetectors) :: pmatrix(npixels_per_sample*nvalids*ndetectors)
    !f2py intent(out)                              :: new_npixels_per_sample
    !f2py intent(out)                              :: status

    character(len=*), intent(in)                   :: band
    integer, intent(in)                            :: nslices
    integer*8, intent(in)                          :: nvalids
    integer, intent(in)                            :: npointings(nslices)
    integer, intent(in)                            :: nsamples_tot
    integer, intent(in)                            :: compression_factor(nslices)
    real(p), intent(in)                            :: delay(nslices)
    integer, intent(in)                            :: fine_sampling_factor
    logical, intent(in)                            :: oversampling
    real(p), intent(in), dimension(nsamples_tot)   :: time, ra, dec, pa, chop
    logical*1, intent(in), dimension(nsamples_tot) :: masked, removed
    character(len=*), intent(in)                   :: method
    logical*1, intent(in)                          :: detector_mask(nrows,ncolumns)
    integer, intent(in)                            :: nrows
    integer, intent(in)                            :: ncolumns
    integer, intent(in)                            :: ndetectors
    real(p), intent(in)                            :: detector_center(2,nrows,ncolumns)
    real(p), intent(in)                            :: detector_corner(2,4,nrows,ncolumns)
    real(p), intent(in)                            :: detector_area(nrows,ncolumns)
    real(p), intent(in)                            :: distortion_yz(2,3,3,3)
    integer, intent(in)                            :: npixels_per_sample
    character(len=*), intent(in)                   :: header
    type(PointingElement), intent(inout)           :: pmatrix(npixels_per_sample,nvalids,ndetectors)
    integer, intent(out)                           :: new_npixels_per_sample
    integer, intent(out)                           :: status

    class(PacsObservation), allocatable :: obs
    class(PacsInstrument), allocatable  :: pacs
    integer                             :: nx, ny, nsamples_expected, method_

    ! initialise observations
    allocate(obs)
    call obs%init_with_variables(time, ra, dec, pa, chop, masked, removed, npointings, compression_factor, delay, status)
    if (status /= 0) return

    ! initialise pacs instrument
    allocate (pacs)
    call pacs%init_with_variables(band, detector_mask, fine_sampling_factor, status, detector_center_all=detector_center,          &
                                  detector_corner_all=detector_corner, detector_area_all=detector_area, distortion_yz=distortion_yz)
    if (status /= 0) return

    ! check number of detectors
    if (pacs%ndetectors /= ndetectors) then
        status = 1
        write (ERROR_UNIT,'(a,2(i0,a))') "The specified number of detectors '", ndetectors, "' is incompatible with that from the i&
              &nput detector mask '", pacs%ndetectors, "'."
        return
    end if

    ! check number of fine samples
    if (oversampling) then
        nsamples_expected = sum(obs%slice%nvalids * compression_factor)*fine_sampling_factor
    else
        nsamples_expected = sum(obs%slice%nvalids)
    end if
    if (nvalids /= nsamples_expected) then
        status = 1
        write (ERROR_UNIT,'(a,2(i0,a))') "The specified total number of samples '", nvalids, "' is incompatible with that from the &
              &observations '", nsamples_expected, "'."
        return
    end if

    ! get the size of the map
    call ft_read_keyword(header, 'naxis1', nx, status=status)
    if (status /= 0) return
    call ft_read_keyword(header, 'naxis2', ny, status=status)
    if (status /= 0) return

    ! get method id
    select case (method)

        case ('nearest')
            method_ = NEAREST_NEIGHBOUR

        case ('sharp')
            method_ = SHARP_EDGES

        case default
            write (ERROR_UNIT, '(a)') 'Unknown projection method ' // method // '.'
            status = 1
            return
    
    end select

    ! compute the projector
    call pacs%compute_projection(method_, obs, oversampling, header, nx, ny, pmatrix, new_npixels_per_sample, status)

end subroutine pacs_pointing_matrix


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_uv2ad(u, v, ncoords, ra, dec, pa, chop, nsamples, distortion_yz, a, d)

    !f2py threadsafe
    !f2py intent(in)   :: u, v, ra, dec, pa, chop, distortion_yz
    !f2py intent(hide) :: ncoords = size(u)
    !f2py intent(hide) :: nsamples = size(ra)
    !f2py intent(out)  :: a, d

    use module_pacsinstrument, only : uv2yz, yz2ad
    use module_tamasis,        only : p
    implicit none

    integer, intent(in)  :: ncoords, nsamples
    real(p), intent(in)  :: u(ncoords), v(ncoords), ra(nsamples), dec(nsamples), pa(nsamples), chop(nsamples)
    real(p), intent(in)  :: distortion_yz(2,3,3,3)
    real(p), intent(out) :: a(ncoords,nsamples), d(ncoords,nsamples)

    real(p) :: coords(2,ncoords), coords_uv(2,ncoords)
    integer :: isample

    coords_uv(1,:) = u
    coords_uv(2,:) = v
    !$omp parallel do private(coords)
    do isample = 1, nsamples
        coords = uv2yz(coords_uv, distortion_yz, chop(isample))
        coords = yz2ad(coords, ra(isample), dec(isample), pa(isample))
        a(:,isample) = coords(1,:)
        d(:,isample) = coords(2,:)
    end do
    !$omp end parallel do

end subroutine pacs_uv2ad


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_multiplexing_direct(signal, multiplexed, fine_sampling_factor, ij, nsamples, ndetectors)

    use module_pacsinstrument, only : multiplexing_direct
    use module_tamasis,        only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)       :: signal
    !f2py intent(inout)    :: multiplexed
    !f2py intent(in)       :: fine_sampling_factor
    !f2py intent(in)       :: ij
    !f2py intent(hide)     :: nsamples = shape(signal,0)
    !f2py intent(hide)     :: ndetectors = shape(signal,1)

    real(p), intent(in)    :: signal(nsamples, ndetectors)
    integer*8, intent(in)  :: nsamples
    integer, intent(in)    :: ndetectors, fine_sampling_factor, ij(2, ndetectors)
    real(p), intent(inout) :: multiplexed(nsamples/fine_sampling_factor, ndetectors)

    call multiplexing_direct(signal, multiplexed, fine_sampling_factor, ij)

end subroutine pacs_multiplexing_direct


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_multiplexing_transpose(multiplexed, signal, fine_sampling_factor, ij, nsamples, ndetectors)

    use module_pacsinstrument, only : multiplexing_transpose
    use module_tamasis,        only : p
    implicit none

    !f2py threadsafe
    !f2py intent(in)       :: multiplexed
    !f2py intent(inout)    :: signal
    !f2py intent(in)       :: fine_sampling_factor
    !f2py intent(in)       :: ij
    !f2py intent(hide)     :: nsamples = shape(signal,0)
    !f2py intent(hide)     :: ndetectors = shape(signal,1)
    
    integer*8, intent(in)  :: nsamples
    integer, intent(in)    :: ndetectors, fine_sampling_factor, ij(2, ndetectors)
    real(p), intent(inout) :: signal(nsamples, ndetectors)
    real(p), intent(in)    :: multiplexed(nsamples/fine_sampling_factor, ndetectors)

    call multiplexing_transpose(multiplexed, signal, fine_sampling_factor, ij)

end subroutine pacs_multiplexing_transpose


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_bitmask(mask, nsamples, ndetectors, bitmask)

    implicit none

    !f2py intent(in)       :: mask
    !f2py intent(hide)     :: nsamples = shape(mask,0)
    !f2py intent(hide)     :: ndetectors = shape(mask,1)
    !f2py intent(out)      :: bitmask

    logical*1, intent(in)  :: mask(nsamples, ndetectors)
    integer, intent(in)    :: nsamples, ndetectors
    integer*4, intent(out) :: bitmask((nsamples-1)/32+1,ndetectors)

    integer :: idetector, isample

    bitmask = 0

    !$omp parallel do
    do idetector = 1, ndetectors
        do isample = 1, nsamples
            if (mask(isample,idetector)) then
                bitmask((isample-1)/32+1,idetector) = ibset(bitmask((isample-1)/32+1,idetector), modulo(isample-1,32))
            end if
        end do
    end do
    !$omp end parallel do

end subroutine pacs_bitmask


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_pack_real(input, ndata, ncolumns, nrows, ndetectors, mask, output)

    use module_tamasis, only : p
    implicit none

    !f2py intent(in)      :: input(ndata,ncolumns,nrows)
    !f2py intent(hide)    :: ndata=shape(input,0)
    !f2py intent(hide)    :: ncolumns=shape(input,1)
    !f2py intent(hide)    :: nrows=shape(input,2)
    !f2py intent(in)      :: ndetectors
    !f2py intent(in)      :: mask(ncolumns,nrows)
    !f2py intent(out)     :: output(ndata,ndetectors)

    integer, intent(in)   :: ndata, ncolumns, nrows, ndetectors
    real(p), intent(in)   :: input(ndata,ncolumns,nrows)
    logical*1, intent(in) :: mask(ncolumns,nrows)
    real(p), intent(out)  :: output(ndata,ndetectors)

    integer :: nblocks, idetector, i, j, k

    if (nrows == 32) then
        nblocks = 8
    else
        nblocks = 2
    end if

    idetector = 1
    do k = 1, nblocks
        do i = (k - 1) / 4 * 16 + 1, (k - 1) / 4 * 16 + 16
            do j = modulo(k - 1, 4) * 16 + 1, modulo(k - 1, 4) * 16 + 16 
                if (mask(j,i)) cycle
                output(:,idetector) = input(:,j,i)
                idetector = idetector + 1
            end do
        end do
    end do
    
end subroutine pacs_pack_real


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_pack_int8(input, ndata, ncolumns, nrows, ndetectors, mask, output)

    use module_tamasis, only : p
    implicit none

    !f2py intent(in)       :: input(ndata,ncolumns,nrows)
    !f2py intent(hide)     :: ndata=shape(input,0)
    !f2py intent(hide)     :: ncolumns=shape(input,1)
    !f2py intent(hide)     :: nrows=shape(input,2)
    !f2py intent(in)       :: ndetectors
    !f2py intent(in)       :: mask(ncolumns,nrows)
    !f2py intent(out)      :: output(ndata,ndetectors)

    integer, intent(in)    :: ndata, ncolumns, nrows, ndetectors
    logical*1, intent(in)  :: input(ndata,ncolumns,nrows)
    logical*1, intent(in)  :: mask(ncolumns,nrows)
    logical*1, intent(out) :: output(ndata,ndetectors)

    integer :: nblocks, idetector, i, j, k

    if (nrows == 32) then
        nblocks = 8
    else
        nblocks = 2
    end if

    idetector = 1
    do k = 1, nblocks
        do i = (k - 1) / 4 * 16 + 1, (k - 1) / 4 * 16 + 16
            do j = modulo(k - 1, 4) * 16 + 1, modulo(k - 1, 4) * 16 + 16 
                if (mask(j,i)) cycle
                output(:,idetector) = input(:,j,i)
                idetector = idetector + 1
            end do
        end do
    end do
    
end subroutine pacs_pack_int8


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_unpack_real(input, ndata, ndetectors, ncolumns, nrows, mask, output)

    use module_tamasis, only : p
    implicit none

    !f2py intent(in)      :: input(ndata,ndetectors)
    !f2py intent(hide)    :: ndata=shape(input,0)
    !f2py intent(hide)    :: ndetectors=shape(input,1)
    !f2py intent(in)      :: ncolumns
    !f2py intent(in)      :: nrows
    !f2py intent(in)      :: mask(ncolumns,nrows)
    !f2py intent(out)     :: output(ndata,ncolumns,nrows)

    integer, intent(in)   :: ndata, ndetectors, ncolumns, nrows
    real(p), intent(in)   :: input(ndata,ndetectors)
    logical*1, intent(in) :: mask(ncolumns,nrows)
    real(p), intent(out)  :: output(ndata,ncolumns,nrows)

    integer :: nblocks, idetector, i, j, k

    if (nrows == 32) then
        nblocks = 8
    else
        nblocks = 2
    end if

    idetector = 1
    do k = 1, nblocks
        do i = (k - 1) / 4 * 16 + 1, (k - 1) / 4 * 16 + 16
            do j = modulo(k - 1, 4) * 16 + 1, modulo(k - 1, 4) * 16 + 16 
                if (mask(j,i)) then
                    output(:,j,i) = 0
                    cycle
                end if
                output(:,j,i) = input(:,idetector)
                idetector = idetector + 1
            end do
        end do
    end do

end subroutine pacs_unpack_real


!-----------------------------------------------------------------------------------------------------------------------------------


subroutine pacs_unpack_int8(input, ndata, ndetectors, ncolumns, nrows, mask, output)

    use module_tamasis, only : p
    implicit none

    !f2py intent(in)       :: input(ndata,ndetectors)
    !f2py intent(hide)     :: ndata=shape(input,0)
    !f2py intent(hide)     :: ndetectors=shape(input,1)
    !f2py intent(in)       :: ncolumns
    !f2py intent(in)       :: nrows
    !f2py intent(in)       :: mask(ncolumns,nrows)
    !f2py intent(out)      :: output(ndata,ncolumns,nrows)

    integer, intent(in)    :: ndata, ndetectors, ncolumns, nrows
    logical*1, intent(in)  :: input(ndata,ndetectors)
    logical*1, intent(in)  :: mask(ncolumns,nrows)
    logical*1, intent(out) :: output(ndata,ncolumns,nrows)

    integer :: nblocks, idetector, i, j, k

    if (nrows == 32) then
        nblocks = 8
    else
        nblocks = 2
    end if

    idetector = 1
    do k = 1, nblocks
        do i = (k - 1) / 4 * 16 + 1, (k - 1) / 4 * 16 + 16
            do j = modulo(k - 1, 4) * 16 + 1, modulo(k - 1, 4) * 16 + 16 
                if (mask(j,i)) then
                    output(:,j,i) = .true.
                    cycle
                end if
                output(:,j,i) = input(:,idetector)
                idetector = idetector + 1
            end do
        end do
    end do

end subroutine pacs_unpack_int8
