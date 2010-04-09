module module_deglitching

    use module_math,           only : moment, mad, sigma_clipping
    use module_pointingmatrix, only : pointingelement, backprojection_weighted_roi
    use module_precision,      only : p, sp
    implicit none
    private

    public :: deglitch_l2b


contains


    subroutine deglitch_l2b(pmatrix, nx, ny, timeline, mask, nsigma, use_mad)

        type(pointingelement), intent(in) :: pmatrix(:,:,:)
        integer, intent(in)               :: nx, ny
        real(kind=p), intent(in)          :: timeline(:,:)
        logical(kind=1), intent(inout)    :: mask(:,:)
        real(kind=p), intent(in)          :: nsigma
        logical, intent(in)               :: use_mad

        integer, parameter                :: MIN_SAMPLE_SIZE = 5
        integer         :: npixels_per_sample, npixels_per_frame
        integer         :: ndetectors, ntimes
        integer         :: hitmap(0:nx*ny-1)
        integer         :: roi(2,2,size(timeline,1))
        integer         :: i, j, ipixel, itime, idetector, isample, imap, iv
        integer         :: xmin, xmax, ymin, ymax
        integer         :: nv, nhits_max
        real(kind=p)    :: mv, stddev
        real(kind=p), allocatable :: map(:,:)
        real(kind=p), allocatable :: arrv(:)
        integer, allocatable      :: arrt(:)
        logical, allocatable      :: isglitch(:)
        
        npixels_per_sample = size(pmatrix,1)
        ntimes     = size(pmatrix,2)
        ndetectors = size(pmatrix,3)

        ! compute the largest size of a frame mini-map
        npixels_per_frame = 0
        !$omp parallel do reduction(max:npixels_per_frame) private(xmin,xmax,ymin,ymax)
        do itime=1, ntimes
            xmin = minval(modulo(pmatrix(:,itime,:)%pixel,nx), pmatrix(:,itime,:)%pixel /= -1) + 1
            xmax = maxval(modulo(pmatrix(:,itime,:)%pixel,nx), pmatrix(:,itime,:)%pixel /= -1) + 1
            ymin = minval(pmatrix(:,itime,:)%pixel / nx, pmatrix(:,itime,:)%pixel /= -1) + 1
            ymax = maxval(pmatrix(:,itime,:)%pixel / nx, pmatrix(:,itime,:)%pixel /= -1) + 1
            npixels_per_frame = max(npixels_per_frame, (xmax-xmin+1)*(ymax-ymin+1))
        end do
        !$omp end parallel do

        allocate (map(0:npixels_per_frame-1,ntimes))

        !$omp parallel do
        do itime=1, ntimes
            call backprojection_weighted_roi(pmatrix, nx, timeline, mask, itime, map(:,itime), roi(:,:,itime))
        end do
        !$omp end parallel do

        ! compute hit map, to determine the maximum number of hits
        hitmap = 0
        !$omp parallel do reduction(+:hitmap) private(idetector,isample,ipixel)
        do idetector = 1, ndetectors
            do isample = 1, ntimes
                do ipixel = 1, npixels_per_sample
                    if (pmatrix(ipixel,isample,idetector)%pixel == -1) exit
                    hitmap(pmatrix(ipixel,isample,idetector)%pixel) = hitmap(pmatrix(ipixel,isample,idetector)%pixel) + 1
                end do
            end do
        end do
        !$omp end parallel do

        nhits_max = maxval(hitmap)

        !$omp parallel private(i,j,itime,imap,nv,ipixel,arrv,arrt,isglitch,mv,stddev)
        allocate (arrv(nhits_max))
        allocate (arrt(nhits_max))
        allocate (isglitch(nhits_max))

        ! we loop over each sky pixel
        !$omp do
        do j=1, ny

            do i=1, nx

                ! construct the sample of sky pixels in the minimaps that match the current sky map pixel (i,j)
                nv = 0
                do itime=1, ntimes

                    ! test if the current sky pixel is in the minimap
                    if (i < roi(1,1,itime) .or. i > roi(1,2,itime) .or. &
                        j < roi(2,1,itime) .or. j > roi(2,2,itime)) cycle

                    ! test that the current sky pixel is not NaN in the minimap
                    imap = i-roi(1,1,itime) + (roi(1,2,itime)-roi(1,1,itime)+1) * (j-roi(2,1,itime))
                    if (map(imap,itime) /= map(imap,itime)) cycle

                    ! the sky pixel is in the minimap, let's add it to the sample
                    nv = nv + 1
                    arrv(nv) = map(imap,itime)
                    arrt(nv) = itime

                end do

                ! check we have enough samples
                if (nv < MIN_SAMPLE_SIZE) cycle

                ! sigma clip on arrv
                if (use_mad) then
                    stddev = 1.4826_p * mad(arrv(1:nv),mv)
                    isglitch(1:nv) = abs(arrv(1:nv)-mv) >  nsigma * stddev
                else
                    call sigma_clipping(arrv(1:nv), isglitch(1:nv), nsigma)
                end if
                

                ! update mask
                imap = (i-1) + (j-1)*nx
                do iv=1, nv
                    if (.not. isglitch(iv)) cycle
                    do idetector=1, ndetectors
                        do ipixel=1, npixels_per_sample
                            if (pmatrix(ipixel,arrt(iv),idetector)%pixel == imap) then
                                mask(arrt(iv),idetector) = .true.
                                exit
                            end if
                        end do
                    end do
                end do
            end do
        end do
        !$omp end do
        deallocate (arrv)
        deallocate (arrt)
        deallocate (isglitch)
        !$omp end parallel

        deallocate (map)

    end subroutine deglitch_l2b


end module module_deglitching