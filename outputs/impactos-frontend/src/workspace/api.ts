import type {Draft,Dashboard,FormSummary,FormRow,UploadRow,SubmissionReceipt,Qualitative} from './types';
export class ApiError extends Error {constructor(message:string,public details:unknown[]=[],public status=0){super(message);}}
export class WorkspaceApi {
 constructor(public base:string,private transport:typeof fetch=fetch){this.base=base.replace(/\/+$/,'');}
 async request<T>(path:string,options:RequestInit={},timeout=25000):Promise<T>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{
   const response=await this.transport(`${this.base}${path}`,{...options,signal:controller.signal,headers:options.body instanceof FormData?options.headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
   if(!response.ok){let body;try{body=await response.json();}catch{body=null;}throw new ApiError(body?.error?.message||body?.detail||`تعذر تنفيذ الطلب (${response.status}).`,body?.error?.details||[],response.status);}
   return await response.json() as T;
  }catch(error){if(error instanceof ApiError)throw error;throw new ApiError(error instanceof Error&&error.name==='AbortError'?'استغرق الخادم وقتاً طويلاً. أعد المحاولة.':'تعذر الاتصال بالخادم. تحقق من العنوان وتشغيل الخدمة وإعدادات CORS.');}
  finally{clearTimeout(timer);}
 }
 draft(){return this.request<Draft>('/draft');}
 dashboard(){return this.request<Dashboard>('/dashboard');}
 forms(){return this.request<FormSummary[]>('/forms');}
 form(key:string){return this.request<FormRow>(`/forms/${encodeURIComponent(key)}`);}
 upload(files:File[],extract=false){const data=new FormData();files.forEach(file=>data.append('files',file));return this.request<UploadRow>(`/upload?extract=${extract?'true':'false'}`,{method:'POST',body:data},120000);}
 uploadStatus(id:string){return this.request<UploadRow>(`/upload/${encodeURIComponent(id)}`);}
 extract(id:string){return this.request<UploadRow>(`/upload/${encodeURIComponent(id)}/extract`,{method:'POST'});}
 edit(path:string,data:unknown,method='PATCH'){return this.request<unknown>(`/draft/${path}`,{method,body:JSON.stringify(data)});}
 publish(){return this.request<{published:boolean;unanswered_questions:number;without_definition:string[]}>('/publish',{method:'POST'});}
 submit(key:string,data:Record<string,unknown>){return this.request<SubmissionReceipt>(`/forms/${encodeURIComponent(key)}/submissions`,{method:'POST',body:JSON.stringify({data})});}
 qualitative(){return this.request<Qualitative>('/qualitative',{method:'POST',body:'{}'},120000);}
}
export function normalizeBase(value:string):string{const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('أدخل عنوان HTTP أو HTTPS دون بيانات دخول أو استعلامات.');return url.href.replace(/\/+$/,'');}
