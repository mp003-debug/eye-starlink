"""Pinned MiniMind Llama export, bounded standalone llama2.c adaptation."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
R=Path(__file__).resolve().parents[1];S=R/'build/edge_ai_v2_20261103';V=S/'vendor';O=S/'tiny'
sys.path[:0]=[str(R/'src'),str(R/'tools/deps/edge_ai_host')]
import numpy as np
from eye_tracker.tiny_tokenizer import TinyTokenizer

def tensors():
    raw=(V/'minimind/model.safetensors').read_bytes();size=struct.unpack('<Q',raw[:8])[0];header=json.loads(raw[8:8+size]);base=8+size
    out={}
    for k,v in header.items():
        if k=='__metadata__':continue
        a,b=v['data_offsets'];dtype={'F16':'<f2','F32':'<f4','BF16':'<u2'}[v['dtype']]
        x=np.frombuffer(raw[base+a:base+b],dtype=dtype)
        if v['dtype']=='BF16':x=(x.astype(np.uint32)<<16).view(np.float32)
        out[k]=x.astype(np.float32).reshape(v['shape'])
    return out

def main():
    O.mkdir(exist_ok=True);t=tensors();cfg=json.loads((V/'minimind/config.json').read_text())
    assert (cfg['hidden_size'],cfg['intermediate_size'],cfg['num_hidden_layers'],cfg['num_attention_heads'],cfg['num_key_value_heads'],cfg['vocab_size'])==(512,1408,8,8,2,6400)
    assert cfg['tie_word_embeddings'] and cfg['rope_theta']==1000000 and cfg['rms_norm_eps']==1e-5
    target=O/'minimind_q8.bin';qerror=[]
    with target.open('wb') as f:
        head=struct.pack('<II7iBi',0x616b3432,2,512,1408,8,8,2,6400,256,1,64)
        f.write(head+b'\0'*(256-len(head)))
        for name in ('input_layernorm.weight','post_attention_layernorm.weight'):
            for i in range(8):f.write(t[f'model.layers.{i}.'+name].astype('<f4').tobytes())
        f.write(t['model.norm.weight'].astype('<f4').tobytes())
        names=['model.embed_tokens.weight']+[f'model.layers.{i}.'+kind+'.weight' for kind in ('self_attn.q_proj','self_attn.k_proj','self_attn.v_proj','self_attn.o_proj','mlp.gate_proj','mlp.down_proj','mlp.up_proj') for i in range(8)]
        for name in names:
            w=t[name]
            if name.endswith(('q_proj.weight','k_proj.weight')):
                heads=8 if 'q_proj' in name else 2
                w=w.reshape(heads,2,32,512).transpose(0,2,1,3).reshape(w.shape)
            g=w.reshape(-1,64);scale=np.maximum(np.abs(g).max(1)/127,1e-12)
            q=np.clip(np.rint(g/scale[:,None]),-127,127).astype(np.int8)
            qerror.append(float(np.abs(q*scale[:,None]-g).max()))
            f.write(q.tobytes());f.write(scale.astype('<f4').tobytes())
    src=(V/'llama2c/runq.c').read_text(encoding='utf-8').split('// The Byte Pair Encoding')[0]
    src='/* Adapted for EyeStarlink from llama2.c; see vendor/llama2c/LICENSE. */\n#ifndef _WIN32\n#define _POSIX_C_SOURCE 200809L\n#include <sys/resource.h>\n#endif\n'+src
    src=src.replace('#include <fcntl.h>','#include <fcntl.h>\n#ifdef __ARM_NEON\n#include <arm_neon.h>\n#endif')
    src=src.replace('#include "win.h"','''#include "win.h"
    #include <io.h>
    void *mmap(void *addr,size_t len,int prot,int flags,int fd,ssize_t off){
        (void)addr;(void)prot;(void)flags;
        _setmode(fd,_O_BINARY);if(_lseeki64(fd,off,SEEK_SET)<0)return MAP_FAILED;
        char *p=malloc(len);if(!p)return MAP_FAILED;
        size_t n=0;while(n<len){int r=_read(fd,p+n,(unsigned)(len-n));if(r<=0){free(p);return MAP_FAILED;}n+=r;}return p;
    }
    int munmap(void *addr,size_t len){(void)len;free(addr);return 0;}''')
    src=src.replace('float scale = wmax / Q_MAX;','float scale = wmax > 0 ? wmax / Q_MAX : 1.0f;')
    src=src.replace('10000.0f, head_dim','1000000.0f, head_dim')
    # Stable reductions avoid quantization-bin flips from accumulation order.
    src=src.replace('float ss = 0.0f;', 'double ss = 0.0;').replace('ss += x[j] * x[j];','ss += (double)x[j] * x[j];').replace('ss += 1e-5f;','ss += 1e-5;').replace('ss = 1.0f / sqrtf(ss);','ss = 1.0 / sqrt(ss);').replace('weight[j] * (ss * x[j])','weight[j] * ((float)ss * x[j])')
    src=src.replace('float score = 0.0f;', 'double score = 0.0;').replace('score += q[i] * k[i];', 'score += (double)q[i] * k[i];')
    src=src.replace('w->token_embedding_table = malloc(p->vocab_size * p->dim * sizeof(float));\n    dequantize(w->q_tokens, w->token_embedding_table, p->vocab_size * p->dim);','w->token_embedding_table = NULL; /* Decode only the selected row, saving 12.5 MiB. */')
    src=src.replace('memcpy(x, w->token_embedding_table + token*dim, dim * sizeof(float));','for(int j=0;j<dim;j++) x[j]=w->q_tokens->q[token*dim+j]*w->q_tokens->s[(token*dim+j)/GS];')
    old='''for (int k = 0; k < GS; k++) {
                ival += ((int32_t) x->q[j + k]) * ((int32_t) w->q[in + j + k]);
            }'''
    new='''#ifdef __ARM_NEON
            int32x4_t acc=vdupq_n_s32(0);
            for(int k=0;k<GS;k+=16){
                int8x16_t a=vld1q_s8(x->q+j+k),b=vld1q_s8(w->q+in+j+k);
                acc=vpadalq_s16(acc,vmull_s8(vget_low_s8(a),vget_low_s8(b)));
                acc=vpadalq_s16(acc,vmull_s8(vget_high_s8(a),vget_high_s8(b)));
            }
            int32_t lane[4];vst1q_s32(lane,acc);ival=lane[0]+lane[1]+lane[2]+lane[3];
            #else
            for(int k=0;k<GS;k++)ival+=(int32_t)x->q[j+k]*(int32_t)w->q[in+j+k];
            #endif'''
    assert old in src;src=src.replace(old,new)
    # Hard allowlist on shape/length before mmap; caller also verifies SHA-256.
    src=src.replace('GS = group_size;', '''if(config->dim!=512 || config->hidden_dim!=1408 || config->n_layers!=8 ||
       config->n_heads!=8 || config->n_kv_heads!=2 || config->vocab_size!=6400 ||
       config->seq_len!=256 || group_size!=64 || shared_classifier!=1){fprintf(stderr,"shape rejected\\n");exit(2);}
    GS = group_size;''')
    src=src.replace('fclose(file);\n    // memory map',f'if(*file_size!={target.stat().st_size}){{fprintf(stderr,"size rejected\\n");exit(2);}}\n    fclose(file);\n    // memory map')
    src+='''
double wall_seconds(void){
    #ifdef _WIN32
    return (double)clock()/CLOCKS_PER_SEC;
    #else
    struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);return now.tv_sec+now.tv_nsec*1e-9;
    #endif
}
long peak_rss(void){
    #ifdef _WIN32
    return 0;
    #else
    struct rusage usage;if(getrusage(RUSAGE_SELF,&usage))return -1;return usage.ru_maxrss;
    #endif
}
int main(int argc,char **argv){
    if(argc<4 || argc>5){fprintf(stderr,"model tokens max_new [last_prompt_logits]\\n");return 2;}
    int max_new=atoi(argv[3]);if(max_new<1 || max_new>64)return 2;
    int ids[256],count=0,value;FILE *f=fopen(argv[2],"r");if(!f)return 2;
    while(fscanf(f,"%d",&value)==1){if(count>=192 || value<0 || value>=6400){fclose(f);return 2;}ids[count++]=value;}
    int malformed=!feof(f);fclose(f);if(malformed || count<1 || count+max_new>256)return 2;
    Transformer model={0};model.fd=-1;model.data=MAP_FAILED;build_transformer(&model,argv[1]);
    double wall_begin=wall_seconds();clock_t begin=clock(),first=0;int pos=0,generated=0,token=ids[0];float *logits=NULL;
    for(;pos<count;pos++)logits=forward(&model,ids[pos],pos);
    if(argc==5){f=fopen(argv[4],"wb");if(!f){free_transformer(&model);return 2;}fwrite(logits,sizeof(float),6400,f);fclose(f);}
    first=clock();double prefill_wall=wall_seconds()-wall_begin;
    for(int step=0;step<max_new;step++){
        token=0;for(int j=1;j<6400;j++)if(logits[j]>logits[token])token=j;
        if(token==2 || token==0)break;
        printf("%d\\n",token);fflush(stdout);generated++;
        if(step+1<max_new)logits=forward(&model,token,pos++);
    }
    double pre=(double)(first-begin)/CLOCKS_PER_SEC,total=(double)(clock()-begin)/CLOCKS_PER_SEC;
    fprintf(stderr,"{\\"prompt_tokens\\":%d,\\"generated_tokens\\":%d,\\"prefill_cpu_seconds\\":%.6f,\\"total_cpu_seconds\\":%.6f,\\"prefill_wall_seconds\\":%.6f,\\"total_wall_seconds\\":%.6f,\\"peak_rss_kib\\":%ld}\\n",count,generated,pre,total,prefill_wall,wall_seconds()-wall_begin,peak_rss());
    free_transformer(&model);return 0;
}
'''
    (O/'tiny_run.c').write_text(src,encoding='utf-8')
    (O/'win.h').write_text((V/'llama2c/win.h').read_text(encoding='utf-8').replace('inline ','static inline '),encoding='utf-8')
    cc=__import__('os').environ.get('CC','gcc')
    subprocess.run([cc,'-std=c11','-O3','-Wno-unknown-pragmas','-o',str(O/'tiny_run.exe'),str(O/'tiny_run.c'),'-lm'],check=True)
    from tokenizers import Tokenizer
    golden=Tokenizer.from_file(str(V/'minimind/tokenizer.json'));ours=TinyTokenizer(V/'minimind/tokenizer.json')
    samples=['你好','我想喝水。','请把“水”扩写成一句简短请求。','今天下午想去公园。','Hello world! I\'m fine.',' a  b\n\n next\tword  ', '数字１２３与123，表情😊。','<|im_start|>user\n你好<|im_end|>\n<|im_start|>assistant\n']
    for s in samples:
        assert ours.encode(s)==golden.encode(s,add_special_tokens=False).ids,(s,ours.encode(s),golden.encode(s).ids)
        assert ours.decode(ours.encode(s))==golden.decode(golden.encode(s).ids)
    prompts=['你好，请用一句话介绍自己。','我想喝水','请用一句话表达：请帮我换个姿势。']
    rows=[]
    for i,prompt in enumerate(prompts):
        tokens=ours.prompt(prompt);p=O/f'prompt_{i}.txt';p.write_text(' '.join(map(str,tokens)))
        proc=subprocess.run([str(O/'tiny_run.exe'),str(target),str(p),'32',str(O/f'logits_{i}.f32')],capture_output=True,text=True,timeout=90,check=True)
        ids=list(map(int,proc.stdout.split()));rows.append(dict(prompt=prompt,input_ids=tokens,output_ids=ids,text=ours.decode(ids),metrics=json.loads(proc.stderr)))
    meta=dict(source='jingyaogong/MiniMind2-Small',source_sha256=hashlib.sha256((V/'minimind/model.safetensors').read_bytes()).hexdigest(),quantized_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),bytes=target.stat().st_size,parameters=sum(x.size for x in t.values()),group_size=64,context=256,max_new=64,max_weight_quantization_error=max(qerror),tokenizer_tests=len(samples),desktop_examples=rows,board_tested=False,network_inference=False)
    (O/'local_result.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(meta,ensure_ascii=False))
if __name__=='__main__':main()
