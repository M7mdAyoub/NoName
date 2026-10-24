import {createContext,useContext,useRef,useState,useEffect,type ReactNode} from 'react';
import {WorkspaceApi,ApiError,normalizeBase} from './api';
import {emptyDraft,emptyDashboard} from './model';
import type {Draft,Dashboard,FormSummary,SubmissionReceipt,UploadRow} from './types';
type Store={draft:Draft;dashboard:Dashboard;forms:FormSummary[];uploads:UploadRow[];receipts:SubmissionReceipt[];base:string;connected:boolean;busy:boolean;error:ApiError|null;notice:string;connect:(base:string)=>Promise<boolean>;disconnect:()=>void;refresh:()=>Promise<void>;run:<T>(work:(api:WorkspaceApi)=>Promise<T>,message?:string)=>Promise<T|null>;addUpload:(upload:UploadRow)=>void;addReceipt:(receipt:SubmissionReceipt)=>void;notify:(message:string)=>void;clearError:()=>void};
const Context=createContext<Store|null>(null);
function storedBase(){try{return localStorage.getItem('qiyas-api-url')||'';}catch{return '';}}
export function WorkspaceProvider({children}:{children:ReactNode}){
 const [draft,setDraft]=useState(emptyDraft),[dashboard,setDashboard]=useState(emptyDashboard),[forms,setForms]=useState<FormSummary[]>([]),[uploads,setUploads]=useState<UploadRow[]>([]),[receipts,setReceipts]=useState<SubmissionReceipt[]>([]);
 const [base,setBase]=useState(storedBase),[connected,setConnected]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState<ApiError|null>(null),[notice,notify]=useState('');
 const client=useRef<WorkspaceApi|null>(null),generation=useRef(0);
 useEffect(()=>{try{localStorage.removeItem('impactos-demo-v1');}catch{}},[]);
 function clear(){setDraft(emptyDraft());setDashboard(emptyDashboard());setForms([]);setUploads([]);setReceipts([]);}
 function fail(e:unknown){setError(e instanceof ApiError?e:new ApiError(e instanceof Error?e.message:'تعذر إتمام العملية. أعد المحاولة.'));}
 async function read(api:WorkspaceApi,token:number){
  const [d,values,f]=await Promise.all([api.draft(),api.dashboard(),api.forms()]);
  if(!d||!['results','indicators','forms','definitions','open_questions'].every(key=>Array.isArray(d[key as keyof Draft]))||!Array.isArray(values?.indicators)||!Array.isArray(f))throw new ApiError('استجابة الخادم غير متوافقة مع نسخة API الحالية. راجع إعدادات الاتصال.');
  if(token!==generation.current)return;setDraft(d);setDashboard(values);setForms(f);
 }
 async function connect(value:string){
  const token=++generation.current;clear();setConnected(false);setBusy(true);setError(null);notify('');
  try{const normalized=normalizeBase(value),api=new WorkspaceApi(normalized);await read(api,token);if(token!==generation.current)return false;client.current=api;setBase(normalized);setConnected(true);try{localStorage.setItem('qiyas-api-url',normalized);}catch{}notify('تم الاتصال بالخادم وتحميل البيانات المتاحة.');return true;}
  catch(e){if(token===generation.current){client.current=null;fail(e);}return false;}finally{if(token===generation.current)setBusy(false);}
 }
 async function refresh(){if(!client.current)return;const token=generation.current;setBusy(true);setError(null);try{await read(client.current,token);}catch(e){if(token===generation.current)fail(e);}finally{if(token===generation.current)setBusy(false);}}
 async function run<T,>(work:(api:WorkspaceApi)=>Promise<T>,message?:string):Promise<T|null>{
  const api=client.current,token=generation.current;if(!api){fail(new ApiError('اربط الخادم أولاً لتنفيذ هذه العملية.'));return null;}
  setBusy(true);setError(null);try{const result=await work(api);if(token!==generation.current)return null;if(message)notify(message);return result;}catch(e){if(token===generation.current)fail(e);return null;}finally{if(token===generation.current)setBusy(false);}
 }
 function disconnect(){generation.current++;client.current=null;setConnected(false);setBusy(false);clear();setError(null);notify('تم فصل الاتصال. لم تُحذف أي بيانات من الخادم.');}
 return <Context.Provider value={{draft,dashboard,forms,uploads,receipts,base,connected,busy,error,notice,connect,disconnect,refresh,run,addUpload:upload=>setUploads(old=>[upload,...old.filter(row=>row.id!==upload.id)]),addReceipt:receipt=>setReceipts(old=>[receipt,...old]),notify,clearError:()=>setError(null)}}>{children}</Context.Provider>;
}
export function useWorkspace(){const value=useContext(Context);if(!value)throw Error('WorkspaceProvider is required');return value;}
