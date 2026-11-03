/* EyeStarlink compact MLP: fixed buffers, int8 dot products, ARMv7 NEON.
 * Model is trained elsewhere; no camera, audio, network, or MMIO access. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif
#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
typedef struct { double ws[3],as[3],b[101];int8_t w[75936]; } NN;
static const int dims[4]={1152,64,32,5};
API void *nn_load(const char *path) {
    FILE *f=fopen(path,"rb");if(!f)return NULL;
    char magic[8];NN *n=calloc(1,sizeof(NN));
    if(!n || fread(magic,1,8,f)!=8 || memcmp(magic,"EYEQ8V2\0",8) ||
       fread(n->ws,sizeof(double),3,f)!=3 || fread(n->as,sizeof(double),3,f)!=3 ||
       fread(n->b,sizeof(double),101,f)!=101 || fread(n->w,1,75936,f)!=75936 || fgetc(f)!=EOF) {
        free(n);fclose(f);return NULL;
    }
    fclose(f);
    for(int i=0;i<3;i++)if(!isfinite(n->ws[i]) || n->ws[i]<=0 || !isfinite(n->as[i]) || n->as[i]<=0){free(n);return NULL;}
    for(int i=0;i<101;i++)if(!isfinite(n->b[i])){free(n);return NULL;}
    return n;
}
API void nn_free(void *p){free(p);}
static int32_t dot(const int8_t *a,const int8_t *b,int n) {
    int i=0;int32_t total=0;
#ifdef __ARM_NEON
    int32x4_t sum=vdupq_n_s32(0);
    for(;i+16<=n;i+=16){
        int8x16_t x=vld1q_s8(a+i),y=vld1q_s8(b+i);
        sum=vpadalq_s16(sum,vmull_s8(vget_low_s8(x),vget_low_s8(y)));
        sum=vpadalq_s16(sum,vmull_s8(vget_high_s8(x),vget_high_s8(y)));
    }
    int32_t lanes[4];vst1q_s32(lanes,sum);total=lanes[0]+lanes[1]+lanes[2]+lanes[3];
#endif
    for(;i<n;i++)total+=(int32_t)a[i]*(int32_t)b[i];
    return total;
}
API int nn_forward(void *ptr,const float *input,double *logits) {
    if(!ptr || !input || !logits)return -1;
    NN *n=ptr;double x[1152],next[64];int8_t q[1152];int off=0,boff=0;
    for(int i=0;i<1152;i++){if(!isfinite(input[i]) || input[i]<0 || input[i]>1)return -2;x[i]=(double)input[i]*2-1;}
    for(int l=0;l<3;l++){
        for(int i=0;i<dims[l];i++){
            double a=nearbyint(x[i]/n->as[l]);q[i]=(int8_t)(a>127?127:a< -127?-127:a);
        }
        for(int j=0;j<dims[l+1];j++){
            int32_t s=dot(q,n->w+off+j*dims[l],dims[l]);
            double v=(double)s*n->as[l]*n->ws[l]+n->b[boff+j];
            next[j]=(l<2 && v<0)?0:v;
        }
        off+=dims[l]*dims[l+1];boff+=dims[l+1];memcpy(x,next,dims[l+1]*sizeof(double));
    }
    memcpy(logits,x,5*sizeof(double));return 0;
}
API const char *nn_backend(void){
#ifdef __ARM_NEON
    return "armv7_neon_int8";
#else
    return "portable_int8";
#endif
}
