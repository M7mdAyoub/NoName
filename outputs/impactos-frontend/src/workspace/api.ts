import type {Draft,Dashboard,FormSummary,FormRow,FormSchema,UploadRow,SubmissionReceipt,Qualitative,PublishResult} from './types';
/** `inline`: the screen that ran the request shows this error itself, so the global banner stays quiet. */
export class ApiError extends Error {inline=false;constructor(message:string,public details:unknown[]=[],public status=0){super(message);}}
export class WorkspaceApi {
 // The default calls the global fetch as a plain function: stored as a method and called as
 // this.transport(...), the browser's fetch throws "Illegal invocation" before sending anything.
 constructor(public base:string,private transport:typeof fetch=(input,init)=>fetch(input,init)){this.base=base.replace(/\/+$/,'');}
 async request<T>(path:string,options:RequestInit={},timeout=25000):Promise<T>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{
   const response=await this.transport(`${this.base}${path}`,{...options,signal:controller.signal,headers:options.body instanceof FormData?options.headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});
   if(!response.ok){let body;try{body=await response.json();}catch{body=null;}throw new ApiError(body?.error?.message||body?.detail||`تعذر تنفيذ الطلب (${response.status}).`,body?.error?.details||[],response.status);}
   if(response.status===204)return undefined as T;
   return await response.json() as T;
  }catch(error){if(error instanceof ApiError)throw error;throw new ApiError(error instanceof Error&&error.name==='AbortError'?'استغرق الخادم وقتاً طويلاً. أعد المحاولة.':'تعذر الاتصال بالخادم. تحقق من العنوان وتشغيل الخدمة وإعدادات CORS.');}
  finally{clearTimeout(timer);}
 }
 draft(){return this.request<Draft>('/draft');}
 dashboard(){return this.request<Dashboard>('/dashboard');}
 forms(){return this.request<FormSummary[]>('/forms');}
 form(key:string){return this.request<FormRow>(`/forms/${encodeURIComponent(key)}`);}
 upload(files:File[],extract=false){const data=new FormData();files.forEach(file=>data.append('files',file));return this.request<UploadRow>(`/upload?extract=${extract?'true':'false'}`,{method:'POST',body:data},120000);}
 /** Status only: the parsed document (`ir`) can be large and the screens never show it. */
 uploadStatus(id:string){return this.request<UploadRow>(`/upload/${encodeURIComponent(id)}?ir=false`);}
 extract(id:string){return this.request<UploadRow>(`/upload/${encodeURIComponent(id)}/extract`,{method:'POST'});}
 edit(path:string,data:unknown,method='PATCH'){return this.request<unknown>(`/draft/${path}`,{method,body:JSON.stringify(data)});}
 /** Form builder: create a draft form (the server makes its key from the title). */
 createForm(title:string,schema?:Omit<FormSchema,'title'>){return this.request<FormRow>('/draft/forms',{method:'POST',body:JSON.stringify(schema?{title,schema}:{title})});}
 saveForm(key:string,schema:FormSchema){return this.request<FormRow>(`/draft/forms/${encodeURIComponent(key)}`,{method:'PATCH',body:JSON.stringify({schema})});}
 /** Only draft forms that no calculation rule reads can be deleted (409 otherwise). */
 deleteForm(key:string){return this.request<void>(`/draft/forms/${encodeURIComponent(key)}`,{method:'DELETE'}).then(()=>true);}
 /** Drops a draft rule: the indicator is then published without one and shows as not computable. */
 deleteDefinition(indicatorId:string){return this.request<void>(`/draft/definitions/${encodeURIComponent(indicatorId)}`,{method:'DELETE'}).then(()=>true);}
 publish(){return this.request<PublishResult>('/publish',{method:'POST'});}
 submit(key:string,data:Record<string,unknown>){return this.request<SubmissionReceipt>(`/forms/${encodeURIComponent(key)}/submissions`,{method:'POST',body:JSON.stringify({data})});}
 qualitative(){return this.request<Qualitative>('/qualitative',{method:'POST',body:'{}'},120000);}
}
export function normalizeBase(value:string):string{const url=new URL(value);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error('أدخل عنوان HTTP أو HTTPS دون بيانات دخول أو استعلامات.');return url.href.replace(/\/+$/,'');}
/** The page's own server: the backend serves the built app at /app/, and the Vite dev server proxies the API. */
export function sameOriginBase(location:Pick<Location,'protocol'|'origin'>=window.location):string|null{return ['http:','https:'].includes(location.protocol)?location.origin:null;}
