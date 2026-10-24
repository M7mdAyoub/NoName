import {useId,useRef,useEffect,type ReactNode} from 'react';
import {X,Inbox,ArrowUpLeft,CheckCircle2,AlertCircle,Search} from 'lucide-react';
import {statusLabels} from './model';
import {ApiError} from './api';
export function Logo(){return <span className="q-logo" translate="no"><span className="q-symbol" aria-hidden="true"><i/><i/><i/></span><span>قياس<small>Qiyas</small></span></span>;}
export function Heading({title,description,action}:{title:string;description:string;action?:ReactNode}){return <div className="q-heading"><div><h1>{title}</h1><p>{description}</p></div>{action&&<div className="q-heading-action">{action}</div>}</div>;}
export function Status({value}:{value:string}){return <span className={`q-status q-status-${value}`}><i/>{statusLabels[value]||value}</span>;}
export function EmptyState({title,description,children,icon}:{title:string;description:string;children?:ReactNode;icon?:ReactNode}){return <div className="q-empty"><span className="q-empty-icon">{icon||<Inbox size={27}/>}</span><h3>{title}</h3><p>{description}</p>{children&&<div>{children}</div>}</div>;}
export function External({href,children}:{href:string;children:ReactNode}){return <a className="q-external" href={href} target="_blank" rel="noreferrer">{children}<ArrowUpLeft size={16} aria-hidden="true"/><span className="q-sr-only"> (يفتح في نافذة جديدة)</span></a>;}
export function ErrorNotice({error,clear}:{error:ApiError|null;clear:()=>void}){if(!error)return null;return <div className="q-error" role="alert"><AlertCircle size={21}/><div><strong>تعذر إتمام العملية</strong><p dir="auto">{error.message}</p>{error.details.length>0&&<details><summary>عرض التفاصيل</summary><ul>{error.details.map((item,index)=><li key={index} dir="auto">{typeof item==='string'?item:JSON.stringify(item)}</li>)}</ul></details>}</div><button className="q-icon-btn" onClick={clear} aria-label="إغلاق رسالة الخطأ"><X size={18}/></button></div>;}
export function Dialog({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:ReactNode;wide?:boolean}){
 const ref=useRef<HTMLDialogElement>(null),id=useId();
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return()=>dialog?.close();},[]);
 return <dialog ref={ref} className={`q-dialog ${wide?'q-dialog-wide':''}`} aria-labelledby={id} onCancel={e=>{e.preventDefault();onClose();}}><div className="q-dialog-head"><h2 id={id}>{title}</h2><button className="q-icon-btn" onClick={onClose} aria-label="إغلاق النافذة"><X size={22}/></button></div><div className="q-dialog-content">{children}</div></dialog>;
}
export function SearchBox({value,onChange,label}:{value:string;onChange:(value:string)=>void;label:string}){return <label className="q-search"><Search size={18}/><input aria-label={label} autoComplete="off" value={value} onChange={e=>onChange(e.target.value)} placeholder={`${label}…`}/>{value&&<button className="q-icon-btn" onClick={()=>onChange('')} aria-label="مسح البحث"><X size={16}/></button>}</label>;}
export function Notice({children}:{children:ReactNode}){return <div className="q-notice"><CheckCircle2 size={18}/><p>{children}</p></div>;}
export function count(value:number){return new Intl.NumberFormat('ar-JO').format(value);}
