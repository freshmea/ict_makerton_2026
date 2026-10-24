#include <cuda_runtime.h>
#include <stdlib.h>
// Block reduction replaces two global atomics per pixel with two per block.
__global__ void stats(const unsigned char *cur,const unsigned char *prev,unsigned int *out,int n) {
    __shared__ unsigned int sums[256],diffs[256];
    int tid=threadIdx.x,i=blockIdx.x*blockDim.x+tid;
    sums[tid]=i<n?cur[i]:0;diffs[tid]=i<n?(unsigned int)abs((int)cur[i]-(int)prev[i]):0;__syncthreads();
    for(int step=128;step;step>>=1){if(tid<step){sums[tid]+=sums[tid+step];diffs[tid]+=diffs[tid+step];}__syncthreads();}
    if(tid==0){atomicAdd(out,sums[0]);atomicAdd(out+1,diffs[0]);}
}
struct Scratch {
    unsigned char *a,*b;unsigned int *sum;cudaStream_t stream;bool ready;
    Scratch():a(NULL),b(NULL),sum(NULL),stream(0),ready(false){
        if(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking)!=cudaSuccess)return;
        if(cudaMalloc((void**)&a,320*240)!=cudaSuccess||cudaMalloc((void**)&b,320*240)!=cudaSuccess||cudaMalloc((void**)&sum,2*sizeof(unsigned int))!=cudaSuccess)return;
        ready=true;
    }
    ~Scratch(){if(stream)cudaStreamSynchronize(stream);cudaFree(a);cudaFree(b);cudaFree(sum);if(stream)cudaStreamDestroy(stream);}
};
extern "C" int nano_cuda_stats(const unsigned char *cur,const unsigned char *prev,int n,double *mean,double *motion) {
    if(n<=0||n>320*240)return -1;
    static thread_local Scratch scratch;
    if(!scratch.ready)return -1;
    unsigned int host[2]={0,0};
    if(cudaMemcpyAsync(scratch.a,cur,n,cudaMemcpyHostToDevice,scratch.stream)!=cudaSuccess||cudaMemcpyAsync(scratch.b,prev,n,cudaMemcpyHostToDevice,scratch.stream)!=cudaSuccess||cudaMemsetAsync(scratch.sum,0,sizeof(host),scratch.stream)!=cudaSuccess)return -1;
    stats<<<(n+255)/256,256,0,scratch.stream>>>(scratch.a,scratch.b,scratch.sum,n);
    if(cudaGetLastError()!=cudaSuccess||cudaMemcpyAsync(host,scratch.sum,sizeof(host),cudaMemcpyDeviceToHost,scratch.stream)!=cudaSuccess||cudaStreamSynchronize(scratch.stream)!=cudaSuccess)return -1;
    *mean=(double)host[0]/n;*motion=(double)host[1]/n;return 0;
}
