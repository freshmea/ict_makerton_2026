#include <opencv2/opencv.hpp>
#include <opencv2/dnn.hpp>
#include <opencv2/objdetect.hpp>
#include <NvInfer.h>
#include <cuda_runtime_api.h>
#include <fstream>
#include <sstream>
#include <memory>
#include <vector>
#include <cstring>
#include <cmath>
#include <cstdlib>
namespace {
struct Logger: nvinfer1::ILogger {void log(Severity s,const char *m) noexcept override {if(s<=Severity::kERROR)fprintf(stderr,"TensorRT: %s\n",m);}} logger;
struct Detector {
 nvinfer1::IRuntime *runtime=nullptr; nvinfer1::ICudaEngine *engine=nullptr; nvinfer1::IExecutionContext *context=nullptr;
 std::vector<void*> buffers;std::vector<float> output;int input=-1,out=-1;cv::Ptr<cv::FaceDetectorYN> face;cv::dnn::Net cpu;
 Detector(){
   cv::setNumThreads(1);
   const char *root=getenv("NANO_MODEL_DIR");std::string dir=root?root:"/opt/300seconds/models";
   std::ifstream f(dir+"/yolox_nano.engine",std::ios::binary);
   if(f){std::vector<char> b((std::istreambuf_iterator<char>(f)),{});runtime=nvinfer1::createInferRuntime(logger);if(runtime)engine=runtime->deserializeCudaEngine(b.data(),b.size());
     if(engine){context=engine->createExecutionContext();buffers.resize(engine->getNbBindings(),nullptr);
       for(int i=0;i<engine->getNbBindings();++i){auto d=engine->getBindingDimensions(i);size_t n=1;for(int j=0;j<d.nbDims;++j){if(d.d[j]<1)throw std::runtime_error("dynamic detector shape rejected");n*=d.d[j];}
         if(engine->getBindingDataType(i)!=nvinfer1::DataType::kFLOAT||cudaMalloc(&buffers[i],n*sizeof(float))!=cudaSuccess)throw std::runtime_error("detector allocation failed");
         if(engine->bindingIsInput(i)){if(n!=3*416*416)throw std::runtime_error("YOLOX input shape mismatch");input=i;}else{out=i;output.resize(n);}}
     }
   }
   if(!context){cpu=cv::dnn::readNet(dir+"/yolox_nano.onnx");cpu.setPreferableBackend(cv::dnn::DNN_BACKEND_OPENCV);cpu.setPreferableTarget(cv::dnn::DNN_TARGET_CPU);}
   try{face=cv::FaceDetectorYN::create(dir+"/yunet.onnx","",cv::Size(320,240),0.8f,0.3f,1000);}catch(const cv::Exception&){face.release();}
 }
 ~Detector(){for(auto p:buffers)if(p)cudaFree(p);if(context)context->destroy();if(engine)engine->destroy();if(runtime)runtime->destroy();}
 std::string infer(const unsigned char *nv12,int width,int height){
   cv::Mat image;cv::cvtColor(cv::Mat(height*3/2,width,CV_8UC1,const_cast<unsigned char*>(nv12)),image,cv::COLOR_YUV2BGR_NV12);
   const float ratio=std::min(416.f/width,416.f/height);cv::Mat small,padded(416,416,CV_8UC3,cv::Scalar(114,114,114));cv::resize(image,small,cv::Size(int(width*ratio),int(height*ratio)));small.copyTo(padded(cv::Rect(0,0,small.cols,small.rows)));
   cv::Mat blob=cv::dnn::blobFromImage(padded,1.0,cv::Size(416,416),cv::Scalar(),false,false,CV_32F);std::vector<float> values;
   if(context){
     if(input<0||out<0||cudaMemcpy(buffers[input],blob.ptr<float>(),3*416*416*sizeof(float),cudaMemcpyHostToDevice)!=cudaSuccess||!context->executeV2(buffers.data())||cudaMemcpy(output.data(),buffers[out],output.size()*sizeof(float),cudaMemcpyDeviceToHost)!=cudaSuccess)throw std::runtime_error("TensorRT inference failed");values=output;
   }else{cpu.setInput(blob);cv::Mat result=cpu.forward();values.assign(result.ptr<float>(),result.ptr<float>()+result.total());}
   const size_t anchors=3549;if(values.size()!=anchors*85)throw std::runtime_error("YOLOX output shape mismatch");
   std::vector<cv::Rect> boxes;std::vector<float> scores;size_t row=0;
   for(int stride:{8,16,32})for(int gy=0;gy<416/stride;++gy)for(int gx=0;gx<416/stride;++gx,++row){
     const float *p=values.data()+row*85;float score=p[4]*p[5];if(!std::isfinite(score)||score<0.45f)continue;
     float cx=(p[0]+gx)*stride/ratio,cy=(p[1]+gy)*stride/ratio,w=std::exp(std::min(p[2],10.f))*stride/ratio,h=std::exp(std::min(p[3],10.f))*stride/ratio;
     cv::Rect box(int(cx-w/2),int(cy-h/2),int(w),int(h));box&=cv::Rect(0,0,width,height);if(box.area()>0){boxes.push_back(box);scores.push_back(score);}
   }
   std::vector<int> keep;cv::dnn::NMSBoxes(boxes,scores,0.45f,0.45f,keep);std::ostringstream s;
   s<<"{\"backend\":\""<<(context?"tensorrt8-fp16-sm53":"opencv4-cpu")<<"\",\"model\":\"yolox-nano-0.1.1rc0\",\"persons\":[";
   bool first=true;for(int k:keep){if(!first)s<<',';first=false;auto b=boxes[k];s<<"{\"box\":["<<b.x<<','<<b.y<<','<<b.width<<','<<b.height<<"],\"confidence\":"<<scores[k]<<'}';}
   s<<"],\"faces\":[";
   if(face){cv::Mat faces;face->setInputSize(image.size());face->detect(image,faces);for(int i=0;i<faces.rows;++i){if(i)s<<',';auto p=faces.ptr<float>(i);s<<"{\"box\":["<<p[0]<<','<<p[1]<<','<<p[2]<<','<<p[3]<<"],\"confidence\":"<<p[14]<<'}';}}
   s<<"],\"pose\":\"not_enabled\",\"identity\":\"not_inferred\",\"attention\":\"not_inferred\"}";return s.str();
 }
};
}
extern "C" void *nano_detector_open(){try{return new Detector();}catch(const std::exception&e){fprintf(stderr,"detector: %s\n",e.what());return nullptr;}}
extern "C" int nano_detector_infer(void *p,const unsigned char *data,int width,int height,char *out,int cap){try{if(width!=320||height!=240)return -1;auto s=static_cast<Detector*>(p)->infer(data,width,height);if((int)s.size()>=cap)return -1;std::memcpy(out,s.c_str(),s.size()+1);return 0;}catch(const std::exception&e){fprintf(stderr,"detector infer: %s\n",e.what());return -1;}}
extern "C" void nano_detector_close(void*p){delete static_cast<Detector*>(p);}
