/* New production callers: leave the original screening recipes/binaries intact. */
#define _POSIX_C_SOURCE 200809L
#include <mpi.h>
#include <fftw3-mpi.h>
#include <hdf5.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>
#include <limits.h>

static int rank, size;
static void fail(const char *why) {
    fprintf(stderr, "production rank %d: %s\n", rank, why); fflush(stderr);
    MPI_Abort(MPI_COMM_WORLD, 1); exit(1);
}
#define H5(call) do { if ((call)<0) fail(#call); } while (0)
static uint64_t number(const char *text) {
    char *end; unsigned long long value;
    if (!text || text[0]<'0' || text[0]>'9') fail("invalid integer");
    value=strtoull(text, &end, 10);
    if (*end || value>INT64_MAX) fail("integer outside supported range");
    return (uint64_t)value;
}
static uint64_t multiply(uint64_t a, uint64_t b) {
    if (b && a>(uint64_t)PTRDIFF_MAX/b) fail("size multiplication overflow");
    return a*b;
}
static double initial(uint64_t index) { return sin((double)(index%104729)*0.001); }

static void qualify(void) {
    const int n=131072;
    int *a=malloc(n*sizeof(int)), *b=malloc(n*sizeof(int)), good=1, all;
    if (!a || !b) fail("qualification allocation");
    for (int i=0;i<n;i++) a[i]=rank+i;
    MPI_Sendrecv(a,n,MPI_INT,(rank+1)%size,11,b,n,MPI_INT,(rank+size-1)%size,11,
                 MPI_COMM_WORLD,MPI_STATUS_IGNORE);
    for (int i=0;i<n;i++) if(b[i]!=(rank+size-1)%size+i) good=0;
    MPI_Allreduce(&good,&all,1,MPI_INT,MPI_MIN,MPI_COMM_WORLD);
    if(!all) fail("qualification exchange mismatch");
    free(a); free(b);
    if(rank==0) puts("PRODUCTION_RESULT {\"qualification_passed\":true}");
}

static void checkpoint(const char *path, double *data, uint64_t count, uint64_t offset,
                       uint64_t total, int collective, unsigned *actual, unsigned *local_cause,
                       unsigned *global_cause) {
    hid_t access=H5Pcreate(H5P_FILE_ACCESS); H5(access);
    H5(H5Pset_fapl_mpio(access,MPI_COMM_WORLD,MPI_INFO_NULL));
    H5(H5Pset_all_coll_metadata_ops(access,1)); H5(H5Pset_coll_metadata_write(access,1));
    hid_t file=H5Fcreate(path,H5F_ACC_TRUNC,H5P_DEFAULT,access); H5(file);
    hsize_t extent=(hsize_t)total, length=(hsize_t)count, start=(hsize_t)offset;
    hid_t space=H5Screate_simple(1,&extent,NULL), mem=H5Screate_simple(1,&length,NULL);
    H5(space); H5(mem);
    hid_t dataset=H5Dcreate2(file,"state",H5T_IEEE_F64LE,space,H5P_DEFAULT,H5P_DEFAULT,H5P_DEFAULT); H5(dataset);
    H5(H5Sselect_hyperslab(space,H5S_SELECT_SET,&start,NULL,&length,NULL));
    hid_t transfer=H5Pcreate(H5P_DATASET_XFER); H5(transfer);
    H5(H5Pset_dxpl_mpio(transfer,collective?H5FD_MPIO_COLLECTIVE:H5FD_MPIO_INDEPENDENT));
    H5(H5Dwrite(dataset,H5T_NATIVE_DOUBLE,mem,space,transfer,data));
    H5D_mpio_actual_io_mode_t mode;
    uint32_t local, global;
    H5(H5Pget_mpio_actual_io_mode(transfer,&mode));
    H5(H5Pget_mpio_no_collective_cause(transfer,&local,&global));
    *actual=(unsigned)mode; *local_cause=local; *global_cause=global;
    H5(H5Fflush(file,H5F_SCOPE_GLOBAL));
    H5(H5Pclose(transfer)); H5(H5Dclose(dataset)); H5(H5Sclose(mem)); H5(H5Sclose(space));
    H5(H5Fclose(file)); H5(H5Pclose(access));
}

static double restart_check(const char *path, double *expected, uint64_t count,
                            uint64_t offset) {
    double *out=malloc(multiply(count,sizeof(double)));
    if(!out) fail("restart buffer allocation");
    hid_t access=H5Pcreate(H5P_FILE_ACCESS); H5(access);
    H5(H5Pset_fapl_mpio(access,MPI_COMM_WORLD,MPI_INFO_NULL));
    hid_t file=H5Fopen(path,H5F_ACC_RDONLY,access); H5(file);
    hid_t dataset=H5Dopen2(file,"state",H5P_DEFAULT); H5(dataset);
    hid_t space=H5Dget_space(dataset); H5(space);
    hsize_t length=(hsize_t)count,start=(hsize_t)offset;
    hid_t mem=H5Screate_simple(1,&length,NULL); H5(mem);
    H5(H5Sselect_hyperslab(space,H5S_SELECT_SET,&start,NULL,&length,NULL));
    H5(H5Dread(dataset,H5T_NATIVE_DOUBLE,mem,space,H5P_DEFAULT,out));
    double error=0;
    for(uint64_t i=0;i<count;i++) {
        double e=fabs(out[i]-expected[i]);
        if(!isfinite(out[i]) || !isfinite(e)) fail("nonfinite restart");
        if(e>error) error=e;
    }
    free(out); H5(H5Sclose(mem)); H5(H5Sclose(space)); H5(H5Dclose(dataset));
    H5(H5Fclose(file)); H5(H5Pclose(access));
    return error;
}

int main(int argc, char **argv) {
    fprintf(stderr,"PRODUCTION_STAGE stage=before-mpi-init\n"); fflush(stderr);
    MPI_Init(&argc,&argv); MPI_Comm_rank(MPI_COMM_WORLD,&rank); MPI_Comm_size(MPI_COMM_WORLD,&size);
    if(argc==2 && !strcmp(argv[1],"qualify")) {
        qualify(); MPI_Finalize(); return 0;
    }
    /* mode nx ny nz steps checkpoint-every io-elements path preflight */
    if(argc!=10) fail("expected mode nx ny nz steps cadence io-elements path preflight");
    int fft=!strcmp(argv[1],"fft") || !strcmp(argv[1],"integrated");
    int io=strcmp(argv[1],"fft")!=0;
    int collective=strcmp(argv[1],"independent")!=0;
    if(!fft && strcmp(argv[1],"collective") && strcmp(argv[1],"independent")) fail("unknown workload");
    uint64_t nx=number(argv[2]),ny=number(argv[3]),nz=number(argv[4]);
    uint64_t steps64=number(argv[5]),cadence64=number(argv[6]),elements=number(argv[7]);
    if(steps64<1 || steps64>10000 || cadence64<1 || cadence64>steps64) fail("invalid loop bounds");
    int steps=(int)steps64,cadence=(int)cadence64, preflight=(int)number(argv[9]);
    ptrdiff_t local=0,start=0,allocated=0;
    uint64_t count=elements,offset=multiply(elements,(uint64_t)rank),total=multiply(elements,(uint64_t)size);
    uint64_t global_fft=0;
    if(fft) {
        if(nx<(uint64_t)size || nx%(uint64_t)size || ny<2 || nz<2 ||
           multiply(ny,nz)%(uint64_t)size) fail("FFT shape must balance both slab distributions");
        global_fft=multiply(multiply(nx,ny),nz);
        fftw_mpi_init();
        allocated=fftw_mpi_local_size_3d((ptrdiff_t)nx,(ptrdiff_t)ny,(ptrdiff_t)nz,
                                         MPI_COMM_WORLD,&local,&start);
        if(local<1 || allocated<1) fail("empty FFT slab");
        count=multiply(multiply((uint64_t)local,ny),nz)*2;
        offset=multiply(multiply((uint64_t)start,ny),nz)*2;
        total=multiply(global_fft,2);
    }
    if(!count || count>SIZE_MAX/sizeof(double) || total>INT64_MAX/sizeof(double)) fail("invalid data extent");
    uint64_t buffers=fft?multiply((uint64_t)allocated,(io?4:3)*sizeof(fftw_complex)):multiply(count,2*sizeof(double));
    /* Reserve 256 MiB/rank for plans, MPI, HDF5 and runtime allocations. Verify RSS in calibration too. */
    uint64_t estimate=buffers+256ULL*1024*1024;
    if(rank==0) estimate+=multiply(multiply((uint64_t)steps,(uint64_t)size),3*sizeof(unsigned));
    const char *budget=getenv("TRIAL_PRODUCTION_MEMORY_BYTES");
    if(budget && estimate>number(budget)) fail("estimated per-rank memory exceeds qualified budget");
    unsigned long long estimate_in=estimate,estimate_max,local_in=(unsigned long long)local,local_min,local_max;
    MPI_Reduce(&estimate_in,&estimate_max,1,MPI_UNSIGNED_LONG_LONG,MPI_MAX,0,MPI_COMM_WORLD);
    MPI_Reduce(&local_in,&local_min,1,MPI_UNSIGNED_LONG_LONG,MPI_MIN,0,MPI_COMM_WORLD);
    MPI_Reduce(&local_in,&local_max,1,MPI_UNSIGNED_LONG_LONG,MPI_MAX,0,MPI_COMM_WORLD);
    if(preflight) {
        if(rank==0) printf("PRODUCTION_RESULT {\"preflight_passed\":true,\"estimated_rank_bytes\":%llu,"
                          "\"local_slabs_min\":%llu,\"local_slabs_max\":%llu,\"checkpoint_bytes\":%llu}\n",
                          estimate_max,local_min,local_max,(unsigned long long)(io?total*sizeof(double):0));
        if(fft) fftw_mpi_cleanup();
        MPI_Finalize(); return 0;
    }
    double *data=NULL;
    fftw_complex *in=NULL,*out=NULL,*back=NULL;
    fftw_plan forward=NULL,inverse=NULL;
    double plan_start=MPI_Wtime();
    if(fft) {
        in=fftw_alloc_complex(allocated); out=fftw_alloc_complex(allocated); back=fftw_alloc_complex(allocated);
        if(!in || !out || !back) fail("FFT allocation failed");
        forward=fftw_mpi_plan_dft_3d((ptrdiff_t)nx,(ptrdiff_t)ny,(ptrdiff_t)nz,in,out,MPI_COMM_WORLD,FFTW_FORWARD,FFTW_ESTIMATE);
        inverse=fftw_mpi_plan_dft_3d((ptrdiff_t)nx,(ptrdiff_t)ny,(ptrdiff_t)nz,out,back,MPI_COMM_WORLD,FFTW_BACKWARD,FFTW_ESTIMATE);
        if(!forward || !inverse) fail("FFT plan failed");
        data=(double *)in;
    } else {
        data=malloc(multiply(count,sizeof(double)));
        if(!data) fail("HDF5 data allocation failed");
    }
    double planning=MPI_Wtime()-plan_start,planning_max;
    MPI_Reduce(&planning,&planning_max,1,MPI_DOUBLE,MPI_MAX,0,MPI_COMM_WORLD);
    for(uint64_t i=0;i<count;i++) data[i]=initial(offset+i);
    double *times=calloc((size_t)steps,sizeof(double)),*writes=calloc((size_t)steps,sizeof(double));
    double *max_times=calloc((size_t)steps,sizeof(double)),*max_writes=calloc((size_t)steps,sizeof(double));
    unsigned *modes=calloc((size_t)steps,sizeof(unsigned)),*causes=calloc((size_t)steps,sizeof(unsigned));
    unsigned *global_causes=calloc((size_t)steps,sizeof(unsigned));
    if(!times || !writes || !max_times || !max_writes || !modes || !causes || !global_causes) fail("history allocation");
    const double decay=0.999999;
    int checkpoints=0;
    MPI_Barrier(MPI_COMM_WORLD); double loop_start=MPI_Wtime();
    for(int step=0;step<steps;step++) {
        double t=MPI_Wtime();
        if(fft) {
            fftw_execute(forward);
            for(uint64_t i=0;i<count/2;i++) {
                out[i][0]*=decay; out[i][1]*=decay;
            }
            fftw_execute(inverse);
            for(uint64_t i=0;i<count;i++) data[i]=((double *)back)[i]/(double)global_fft;
        } else {
            for(uint64_t i=0;i<count;i++) data[i]=initial(offset+i)+(double)step*0.001;
        }
        times[step]=MPI_Wtime()-t;
        if(io && ((step+1)%cadence==0 || step==steps-1)) {
            t=MPI_Wtime();
            checkpoint(argv[8],data,count,offset,total,collective,&modes[step],&causes[step],&global_causes[step]);
            writes[step]=MPI_Wtime()-t; checkpoints++;
        }
    }
    double loop_local=MPI_Wtime()-loop_start,loop_max;
    MPI_Reduce(&loop_local,&loop_max,1,MPI_DOUBLE,MPI_MAX,0,MPI_COMM_WORLD);
    /* Reductions and output are outside the timed loop. Each phase maximum is
       descriptive; their sum is not the observed whole-loop critical path. */
    MPI_Reduce(times,max_times,steps,MPI_DOUBLE,MPI_MAX,0,MPI_COMM_WORLD);
    MPI_Reduce(writes,max_writes,steps,MPI_DOUBLE,MPI_MAX,0,MPI_COMM_WORLD);
    double error_local=0,error;
    double accumulated_decay=pow(decay,steps);
    for(uint64_t i=0;i<count;i++) {
        double expected=fft?initial(offset+i)*accumulated_decay:initial(offset+i)+(double)(steps-1)*0.001;
        double e=fabs(data[i]-expected);
        if(!isfinite(e)) fail("nonfinite loop state");
        if(e>error_local) error_local=e;
    }
    if(io) {
        double e=restart_check(argv[8],data,count,offset);
        if(e>error_local) error_local=e;
    }
    MPI_Allreduce(&error_local,&error,1,MPI_DOUBLE,MPI_MAX,MPI_COMM_WORLD);
    if(error>1e-8) fail("loop/restart numerical validation failed");
    unsigned *all_modes=NULL,*all_causes=NULL,*all_global_causes=NULL;
    if(rank==0) {
        uint64_t history=multiply((uint64_t)steps,(uint64_t)size);
        all_modes=calloc((size_t)history,sizeof(unsigned)); all_causes=calloc((size_t)history,sizeof(unsigned));
        all_global_causes=calloc((size_t)history,sizeof(unsigned));
        if(!all_modes || !all_causes || !all_global_causes) fail("I/O mode history allocation");
    }
    MPI_Gather(modes,steps,MPI_UNSIGNED,all_modes,steps,MPI_UNSIGNED,0,MPI_COMM_WORLD);
    MPI_Gather(causes,steps,MPI_UNSIGNED,all_causes,steps,MPI_UNSIGNED,0,MPI_COMM_WORLD);
    MPI_Gather(global_causes,steps,MPI_UNSIGNED,all_global_causes,steps,MPI_UNSIGNED,0,MPI_COMM_WORLD);
    struct rusage usage; if(getrusage(RUSAGE_SELF,&usage)) fail("getrusage");
    unsigned long long rss=(unsigned long long)usage.ru_maxrss*1024,rss_max;
    MPI_Reduce(&rss,&rss_max,1,MPI_UNSIGNED_LONG_LONG,MPI_MAX,0,MPI_COMM_WORLD);
    MPI_Barrier(MPI_COMM_WORLD);
    if(rank==0) {
        printf("PRODUCTION_RESULT {\"loop_seconds\":%.17g,\"planning_seconds\":%.17g,\"error\":%.17g,"
               "\"max_rank_rss_bytes\":%llu,\"steps\":%d,\"checkpoints\":%d,\"checkpoint_bytes\":%llu,\"iterations\":[",
               loop_max,planning_max,error,rss_max,steps,checkpoints,(unsigned long long)(io?total*sizeof(double):0));
        for(int i=0;i<steps;i++) printf("%s{\"step\":%d,\"compute_maxrank_seconds\":%.17g,\"write_maxrank_seconds\":%.17g}",
                                       i?",":"",i+1,max_times[i],max_writes[i]);
        printf("],\"io_modes\":["); int first=1;
        for(int r=0;r<size;r++) for(int s=0;s<steps;s++) if(io && ((s+1)%cadence==0 || s==steps-1)) {
            size_t index=(size_t)r*(size_t)steps+(size_t)s;
            printf("%s{\"rank\":%d,\"step\":%d,\"actual_mode\":%u,\"local_cause\":%u,\"global_cause\":%u}",
                   first?"":",",r,s+1,all_modes[index],all_causes[index],all_global_causes[index]); first=0;
        }
        puts("]}"); fflush(stdout);
        if(io && unlink(argv[8])) fail("checkpoint cleanup failed");
    }
    if(fft) {
        fftw_destroy_plan(forward); fftw_destroy_plan(inverse);
        fftw_free(in); fftw_free(out); fftw_free(back); fftw_mpi_cleanup();
    } else free(data);
    free(times); free(writes); free(max_times); free(max_writes);
    free(modes); free(causes); free(global_causes);
    free(all_modes); free(all_causes); free(all_global_causes);
    MPI_Finalize(); return 0;
}
