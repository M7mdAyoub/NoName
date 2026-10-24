import {createContext,useContext,useRef,useState,useEffect,type ReactNode} from 'react';
import {WorkspaceApi,ApiError,normalizeBase,sameOriginBase} from './api';
import {emptyDraft,emptyDashboard} from './model';
import type {Draft,Dashboard,FormSummary,SubmissionReceipt,UploadRow} from './types';
type Store={draft:Draft;dashboard:Dashboard;forms:FormSummary[];uploads:UploadRow[];receipts:SubmissionReceipt[];base:string;connected:boolean;busy:boolean;error:ApiError|null;notice:string;connect:(base:string,quiet?:boolean)=>Promise<boolean>;disconnect:()=>void;refresh:()=>Promise<void>;run:<T>(work:(api:WorkspaceApi)=>Promise<T>,message?:string,options?:{inline?:boolean})=>Promise<T|null>;addUpload:(upload:UploadRow)=>void;addReceipt:(receipt:SubmissionReceipt)=>void;notify:(message:string)=>void;clearError:()=>void;setUnsaved:(message:string|null)=>void;confirmLeave:()=>boolean};
const Context=createContext<Store|null>(null);
function storedBase(){try{return localStorage.getItem('qiyas-api-url')||'';}catch{return '';}}
export function WorkspaceProvider({children}:{children:ReactNode}){
 const [draft,setDraft]=useState(emptyDraft),[dashboard,setDashboard]=useState(emptyDashboard),[forms,setForms]=useState<FormSummary[]>([]),[uploads,setUploads]=useState<UploadRow[]>([]),[receipts,setReceipts]=useState<SubmissionReceipt[]>([]);
 const [base,setBase]=useState(()=>storedBase()||sameOriginBase()||''),[connected,setConnected]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<ApiError|null>(null),[notice,notify]=useState('');
 const client=useRef<WorkspaceApi|null>(null),generation=useRef(0);
 // A screen with unsaved edits (the form builder) registers a message here; reconnecting or disconnecting
 // clears all loaded data, so those actions ask first.
 const unsaved=useRef<string|null>(null);
 function confirmLeave(){return !unsaved.current||window.confirm(unsaved.current);}
 useEffect(()=>{try{localStorage.removeItem('impactos-demo-v1');}catch{}},[]);
 // Connect on load: to the address chosen earlier, else to this page's own server (the backend serves
 // the built app at /app/, and the dev server proxies the API). A failed automatic attempt stays quiet.
 useEffect(()=>{const saved=storedBase(),initial=saved||sameOriginBase();if(initial)void connect(initial,!saved);},[]);
 function clear(){setDraft(emptyDraft());setDashboard(emptyDashboard());setForms([]);setUploads([]);setReceipts([]);}
 function fail(e:unknown,inline=false){const error=e instanceof ApiError?e:new ApiError(e instanceof Error?e.message:'تعذر إتمام العملية. أعد المحاولة.');error.inline=inline;setError(error);}
 async function read(api:WorkspaceApi,token:number){
  const [d,values,f]=await Promise.all([api.draft(),api.dashboard(),api.forms()]);
  if(!d||!['results','indicators','forms','definitions','open_questions'].every(key=>Array.isArray(d[key as keyof Draft]))||!Array.isArray(values?.indicators)||!values?.summary||!Array.isArray(f))throw new ApiError('استجابة الخادم غير متوافقة مع نسخة API الحالية. راجع إعدادات الاتصال.');
  if(token!==generation.current)return;setDraft(d);setDashboard(values);setForms(f);
 }
 async function connect(value:string,quiet=false){
  const token=++generation.current;clear();setConnected(false);setBusy(true);setError(null);notify('');
  try{const normalized=normalizeBase(value),api=new WorkspaceApi(normalized);await read(api,token);if(token!==generation.current)return false;client.current=api;setBase(normalized);setConnected(true);if(!quiet){try{localStorage.setItem('qiyas-api-url',normalized);}catch{}notify('تم الاتصال بالخادم وتحميل البيانات المتاحة.');}return true;}
  catch(e){if(token===generation.current){client.current=null;if(!quiet)fail(e);}return false;}finally{if(token===generation.current)setBusy(false);}
 }
 async function refresh(){if(!client.current)return;const token=generation.current;setBusy(true);setError(null);try{await read(client.current,token);}catch(e){if(token===generation.current)fail(e);}finally{if(token===generation.current)setBusy(false);}}
 async function run<T,>(work:(api:WorkspaceApi)=>Promise<T>,message?:string,options:{inline?:boolean}={}):Promise<T|null>{
  const api=client.current,token=generation.current;if(!api){fail(new ApiError('اربط الخادم أولاً لتنفيذ هذه العملية.'));return null;}
  setBusy(true);setError(null);try{const result=await work(api);if(token!==generation.current)return null;if(message)notify(message);return result;}catch(e){if(token===generation.current)fail(e,options.inline);return null;}finally{if(token===generation.current)setBusy(false);}
 }
 function disconnect(){generation.current++;client.current=null;setConnected(false);setBusy(false);clear();setError(null);try{localStorage.removeItem('qiyas-api-url');}catch{}notify('تم فصل الاتصال. لم تُحذف أي بيانات من الخادم.');}
 return <Context.Provider value={{draft,dashboard,forms,uploads,receipts,base,connected,busy,error,notice,connect,disconnect,refresh,run,addUpload:upload=>setUploads(old=>[upload,...old.filter(row=>row.id!==upload.id)]),addReceipt:receipt=>setReceipts(old=>[receipt,...old]),notify,clearError:()=>setError(null),setUnsaved:(message:string|null)=>{unsaved.current=message;},confirmLeave}}>{children}</Context.Provider>;
}
export function useWorkspace(){const value=useContext(Context);if(!value)throw Error('WorkspaceProvider is required');return value;}
