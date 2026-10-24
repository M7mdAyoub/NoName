import {useState,useEffect,useRef,Fragment} from 'react';
import {ClipboardList,ArrowLeft,Eye,Send,FileText,Plus,ShieldCheck} from 'lucide-react';
import {useWorkspace} from './Context';
import {Heading,EmptyState,Status,Dialog,SearchBox,OriginBadge,ServerError,count,Notice} from './UI';
import {validateFormAnswers,dateLabel,detailText,formsInDefinition,hashParam,sectionGroups} from './model';
import type {FormRow,FormSummary,FieldError,FormField,SubmissionReceipt} from './types';

export default function Collect(){
 const {draft,dashboard,forms,receipts,connected,busy,error,clearError,run,refresh,addReceipt}=useWorkspace();
 const [tab,setTab]=useState('forms'),[query,setQuery]=useState(''),[form,setForm]=useState<FormRow|null>(null),[preview,setPreview]=useState(false),[answers,setAnswers]=useState<Record<string,unknown>>({}),[issues,setIssues]=useState<FieldError[]>([]),[saved,setSaved]=useState<SubmissionReceipt|null>(null),[receipt,setReceipt]=useState<SubmissionReceipt|null>(null),[missing,setMissing]=useState('');
 const wanted=useRef(hashParam('form'));
 const filtered=forms.filter(f=>f.title.toLowerCase().includes(query.toLowerCase()));
 const names:Record<string,string>=Object.fromEntries([...draft.indicators.map(i=>[i.id,i.name]),...forms.map(f=>[f.key,f.title])]);
 const schemaOf=(key:string)=>draft.forms.find(f=>f.key===key)?.schema;

 // #/collect?form=key: once the forms are loaded, open a published form for filling and a draft one as a read-only preview.
 useEffect(()=>{
  const key=wanted.current;
  if(!key||!connected||busy)return;
  wanted.current=null;
  const row=forms.find(f=>f.key===key);
  if(row)void open(row.key,row.status!=='published');else setMissing(key);
 },[connected,busy,forms]);

 /** Indicators this form feeds: the published KPIs on the dashboard, or for a draft form the rules in the draft that read it. */
 function feeds(row:FormSummary):string[]{
  if(row.status==='published')return dashboard.indicators.filter(i=>(i.forms||[]).some(f=>f.key===row.key)).map(i=>i.name);
  return draft.definitions.filter(d=>formsInDefinition(d.definition).includes(row.key)).map(d=>names[d.indicator_id]).filter((name):name is string=>!!name);
 }
 async function open(key:string,readOnly:boolean){clearError();setMissing('');const row=await run(api=>api.form(key));if(row){setForm(row);setPreview(readOnly||row.status!=='published');setAnswers({});setIssues([]);setSaved(null);}}
 async function submit(){if(!form||preview)return;const errors=validateFormAnswers(form.schema,answers);setIssues(errors);if(errors.length){requestAnimationFrame(()=>document.getElementById(`response-${errors[0].field}`)?.focus());return;}const clean=Object.fromEntries(Object.entries(answers).filter(([,value])=>value!==''&&value!=null&&(!Array.isArray(value)||value.length>0)));const result=await run(api=>api.submit(form.key,clean),'تم حفظ الاستجابة في الخادم.',{inline:true});if(result){addReceipt(result);setSaved(result);await refresh();}}
 const field=(f:FormField)=><AnswerField key={f.id} field={f} value={answers[f.id]} onChange={value=>setAnswers(old=>({...old,[f.id]:value}))} error={issues.find(e=>e.field===f.id)?.message} readOnly={preview||busy}/>;

 return <><Heading title="النماذج والبيانات" description="اجمع الإجابات من النماذج المنشورة، واحتفظ بارتباطها بالمؤشرات."/>
 {missing&&<div className="q-callout q-callout-error" role="alert">لم نجد النموذج <bdi>{missing}</bdi> في الخادم. اختر نموذجاً من القائمة.</div>}
 <section className="q-panel"><div className="q-tabs" role="tablist" aria-label="عرض النماذج أو الاستجابات"><button role="tab" aria-selected={tab==='forms'} onClick={()=>setTab('forms')}>النماذج<span className="q-tab-count">{connected?count(forms.length):'—'}</span></button><button role="tab" aria-selected={tab==='receipts'} onClick={()=>setTab('receipts')}>إجابات هذه الجلسة<span className="q-tab-count">{count(receipts.length)}</span></button></div>
 {tab==='forms'?(forms.length?<><div className="q-table-toolbar"><SearchBox value={query} onChange={setQuery} label="ابحث عن نموذج"/><p className="q-field-hint">{count(filtered.length)} نماذج</p></div><div className="q-forms-grid">{filtered.map(row=>{
  const schema=schemaOf(row.key),kpis=feeds(row),shown=kpis.slice(0,3),more=kpis.length-shown.length;
  return <article className="q-form-card" key={row.key}>
   <div className="q-form-card-top"><span className="q-round-icon"><ClipboardList size={23}/></span><div className="q-scr-badges"><OriginBadge origin={schema?.origin} source={schema?.source}/><Status value={row.status}/></div></div>
   <h2 dir="auto">{row.title}</h2>
   <p>{count(row.submissions)} استجابات مسجلة</p>
   <div className="q-scr-feeds"><span>{row.status==='published'?'يغذّي المؤشرات:':'سيغذّي بعد النشر:'}</span>{kpis.length?<ul title={kpis.join('، ')}>{shown.map((name,index)=><li key={index} dir="auto">{name}</li>)}{more>0&&<li className="q-scr-more"><bdi dir="ltr">+{count(more)}</bdi><span className="q-sr-only"> مؤشرات أخرى</span></li>}</ul>:<span className="q-scr-none">لا يغذّي أي مؤشر بعد.</span>}</div>
   <div className="q-form-card-actions"><button className="q-btn" disabled={busy} onClick={()=>open(row.key,true)}><Eye size={17}/>معاينة</button><button className="q-btn q-primary" disabled={busy||row.status!=='published'} onClick={()=>open(row.key,false)}><Plus size={17}/>تعبئة النموذج</button></div>
   {row.status!=='published'&&<p className="q-field-hint">انشر النموذج من <a className="q-scr-text-link" href="#/review">صفحة المراجعة</a> أولاً.</p>}
  </article>;})}</div>{!filtered.length&&<p className="q-inline-empty">لا توجد نماذج تطابق البحث.</p>}</>:<EmptyState title="لا توجد نماذج منشورة بعد" description="تظهر النماذج هنا بعد استخراج الإطار ومراجعته. لا تُنشأ إجابات أو استجابات افتراضية." icon={<ClipboardList size={28}/>}><a className="q-btn" href="#/review">الانتقال إلى المراجعة<ArrowLeft size={17}/></a></EmptyState>):receipts.length?<><div className="q-session-note"><ShieldCheck size={19}/><p>هذه الاستجابات أُرسلت فعلياً إلى الخادم في الجلسة الحالية. سجل الاستجابات الكامل غير متاح عبر API النسخة الحالية.</p></div><div className="q-table-scroll"><table><thead><tr><th>النموذج</th><th>تاريخ الإرسال</th><th>معرّف الاستجابة</th><th>التفاصيل</th></tr></thead><tbody>{receipts.map(row=><tr key={row.id}><td dir="auto">{forms.find(f=>f.key===row.form)?.title||row.form}</td><td>{dateLabel(row.collected_at)}</td><td><bdi className="q-record-id">{row.id}</bdi></td><td><button className="q-btn q-compact" onClick={()=>setReceipt(row)}>عرض الإجابات</button></td></tr>)}</tbody></table></div></>:<EmptyState title="لم تُرسل إجابات في هذه الجلسة" description="اختر نموذجاً منشوراً وأدخل بياناتك. سيظهر تأكيد الإرسال هنا بعد حفظ الاستجابة في الخادم." icon={<FileText size={28}/>}><button className="q-btn" onClick={()=>setTab('forms')}>عرض النماذج<ArrowLeft size={17}/></button></EmptyState>}
 </section>
 {form&&<Dialog title={preview?'معاينة النموذج':'تعبئة النموذج'} onClose={()=>{if(!busy)setForm(null);}} wide>
  <div className="q-live-form-title"><div className="q-scr-badges"><Status value={form.status}/><OriginBadge origin={form.schema.origin} source={form.schema.source}/></div><h3 dir="auto">{form.title}</h3><p>{!preview?'الإجابات مرتبطة بهذا النموذج وتُحفظ في خادم المشروع.':form.status==='published'?'هذه معاينة فقط. لن يتم إرسال إجابات.':'هذا النموذج مسودة، لذا تُعرض معاينته فقط. انشره من صفحة المراجعة ليصبح جاهزاً لجمع البيانات.'}</p></div>
  {saved?<><Notice>تم إرسال الاستجابة وحفظها بنجاح.</Notice><dl className="q-definition-grid"><div><dt>معرّف الاستجابة</dt><dd><bdi className="q-record-id">{saved.id}</bdi></dd></div><div><dt>تاريخ الحفظ</dt><dd>{dateLabel(saved.collected_at)}</dd></div></dl><div className="q-dialog-actions"><button className="q-btn" onClick={()=>{setAnswers({});setSaved(null);setIssues([]);}}>إجابة جديدة</button><button className="q-btn q-primary" onClick={()=>{setForm(null);setTab('receipts');}}>عرض الإجابات المرسلة<ArrowLeft size={18}/></button></div></>:
  <form noValidate onSubmit={e=>{e.preventDefault();submit();}}>
   {sectionGroups(form.schema.fields).map((group,index)=>group.section?<section className="q-scr-form-section" key={index} aria-labelledby={`form-section-${index}`}><h4 id={`form-section-${index}`} dir="auto">{group.section}</h4>{group.fields.map(field)}</section>:<Fragment key={index}>{group.fields.map(field)}</Fragment>)}
   {issues.length>0&&<p className="q-field-error" role="alert">راجع الحقول المحددة أعلاه قبل الإرسال.</p>}
   <ServerError error={error} names={names}/>
   <div className="q-dialog-actions"><button className="q-btn" type="button" disabled={busy} onClick={()=>setForm(null)}>إغلاق</button>{!preview&&<button className="q-btn q-primary" disabled={busy}><Send size={18}/>{busy?'جارٍ الإرسال…':'إرسال الإجابات'}</button>}</div>
  </form>}
 </Dialog>}
 {receipt&&<Dialog title="تفاصيل الاستجابة المرسلة" onClose={()=>setReceipt(null)}><dl className="q-response-data">{Object.entries(receipt.data).map(([field,value])=><div key={field}><dt><bdi>{field}</bdi></dt><dd dir="auto">{Array.isArray(value)?value.join('، '):typeof value==='object'?JSON.stringify(value):String(value)}</dd></div>)}</dl><p className="q-field-hint">حُفظت في {dateLabel(receipt.collected_at)}</p></Dialog>}
 </>;
}
function AnswerField({field,value,onChange,error,readOnly}:{field:FormField;value:unknown;onChange:(value:unknown)=>void;error?:string;readOnly:boolean}){
 const id=`response-${field.id}`,props={id,name:field.id,disabled:readOnly,'aria-invalid':!!error,'aria-describedby':error?`${id}-error`:undefined};
 return <div className="q-answer-field"><label className="q-field-label" htmlFor={field.type.startsWith('select_')?`${id}-0`:id}><span dir="auto">{field.label}{field.required&&<span className="q-required"> *</span>}{field.unit&&<span className="q-unit"> ({field.unit})</span>}</span></label>{field.type.startsWith('select_')?<div className="q-answer-options" role="group" aria-label={field.label}>{field.options.map((option,index)=><label key={option.value} className="q-answer-option"><input type={field.type==='select_one'?'radio':'checkbox'} id={index===0?`${id}-0`:`${id}-${index}`} name={field.id} disabled={readOnly} checked={field.type==='select_one'?value===option.value:Array.isArray(value)&&value.includes(option.value)} aria-invalid={!!error} onChange={e=>onChange(field.type==='select_one'?option.value:e.target.checked?[...(Array.isArray(value)?value:[]),option.value]:(Array.isArray(value)?value:[]).filter(v=>v!==option.value))}/><span dir="auto">{option.label}</span></label>)}</div>:field.type==='text'&&field.qualitative?<textarea {...props} dir="auto" value={String(value??'')} onChange={e=>onChange(e.target.value)} autoComplete="off"/>:<input {...props} dir={field.type==='text'?'auto':'ltr'} type={field.type==='integer'||field.type==='decimal'?'number':field.type==='date'?'date':'text'} step={field.type==='decimal'?'any':undefined} min={field.constraints?.min??undefined} max={field.constraints?.max??undefined} value={String(value??'')} onChange={e=>onChange(field.type==='integer'||field.type==='decimal'?(e.target.value===''?'':Number(e.target.value)):e.target.value)} autoComplete="off"/>}{error&&<p id={`${id}-error`} className="q-field-error" role="alert">{error}</p>}{field.pii&&<p className="q-field-hint"><ShieldCheck size={15}/>حقل شخصي: لا يُستخدم في التحليل النوعي.</p>}</div>;
}
