import {useState,useEffect} from 'react';
import {Upload,CloudUpload,FileText,X,ArrowLeft,RefreshCw,GitBranch,ShieldCheck,FlaskConical,Loader2} from 'lucide-react';
import {useWorkspace} from './Context';
import {Heading,Status,Dialog,count} from './UI';
import {validateFiles,metric,kindLabels,detailText} from './model';
import {WorkspaceApi} from './api';
import type {UploadRow} from './types';

/** Statuses in which the server is still working on the upload; the card polls only while in one of them. */
const WORKING=['uploaded','parsing','extracting'];
const EXTRACTABLE=['parsed','extracted','failed'];
const statLabels:Record<string,string>={blocks:'مقاطع',tables:'جداول',rows:'صفوف',sheets:'أوراق',pages:'صفحات'};
/** A count from the server, or — when the server did not report it (never shown as zero). */
const number=(value:unknown)=>typeof value==='number'?count(value):'—';

export default function Framework({openConnection}:{openConnection:()=>void}){
 const {draft,uploads,base,connected,busy,run,refresh,addUpload,notify}=useWorkspace();
 // pollError: null when the last status check worked, otherwise the server's message (possibly empty).
 const [files,setFiles]=useState<File[]>([]),[issues,setIssues]=useState<string[]>([]),[showUpload,setShowUpload]=useState(!draft.indicators.length),[active,setActive]=useState<UploadRow|null>(()=>uploads[0]||null),[pollError,setPollError]=useState<string|null>(null),[confirm,setConfirm]=useState(false);
 // Same rule as the server: once anything is published, extraction would replace it and is refused.
 const published=draft.indicators.some(i=>i.status==='published')||draft.forms.some(f=>f.status==='published'),hasDraft=draft.results.length>0||draft.indicators.length>0||draft.forms.some(f=>f.status==='draft');

 // Poll while the server reads or extracts. The timer is cleared on unmount and whenever the status changes;
 // polling ends by itself once the upload is parsed, extracted or failed. The check is quiet: it does not go
 // through run(), so it neither disables the page's buttons nor clears an error the user is reading.
 useEffect(()=>{
  if(!active||!WORKING.includes(active.status)||!connected||!base)return;
  let cancelled=false;
  const timer=setTimeout(async()=>{
   try{const row=await new WorkspaceApi(base).uploadStatus(active.id);if(!cancelled)await apply(row);}
   catch(e){if(!cancelled)setPollError(e instanceof Error?e.message:'');}
  },2500);
  return()=>{cancelled=true;clearTimeout(timer);};
 },[active,connected,base]);
 // Disconnecting or connecting to another server empties the session's uploads: drop the card with them,
 // so it never polls an upload that belongs to a different server.
 useEffect(()=>{if(active&&!uploads.some(row=>row.id===active.id)){setActive(null);setPollError(null);}},[uploads]);

 /** Show the latest server state of an upload; once extracted, reload the draft it produced (also in test mode). */
 async function apply(row:UploadRow){
  addUpload(row);setActive(row);setPollError(null);
  if(row.status==='extracted'){setShowUpload(false);await refresh();}
 }
 function choose(incoming:FileList|null){const list=Array.from(incoming||[]);setFiles(list);setIssues(validateFiles(list));}
 // The server answers 201 also when it could not read the files (status failed): only a real parse gets the success message.
 async function send(){const errors=validateFiles(files);setIssues(errors);if(errors.length)return;if(!connected){openConnection();return;}const row=await run(api=>api.upload(files,false));if(row){addUpload(row);setActive(row);setFiles([]);setPollError(null);if(row.status==='parsed')notify('تم رفع الملفات وقراءتها.');}}
 async function extract(row:UploadRow){setConfirm(false);const response=await run(api=>api.extract(row.id));if(response)await apply(response);}
 async function update(row:UploadRow){const updated=await run(api=>api.uploadStatus(row.id));if(updated)await apply(updated);}

 const extraction=active?.extraction||null,counts=extraction?.counts||{},problems=Array.isArray(extraction?.problems)?extraction.problems:[];
 const mock=extraction?.mode==='mock',extracted=active?.status==='extracted';
 const aiForms=typeof counts.forms==='number'&&typeof counts.forms_from_documents==='number'?counts.forms-counts.forms_from_documents:null;
 const withoutRule=typeof counts.indicators==='number'&&typeof counts.definitions==='number'?counts.indicators-counts.definitions:null;
 const canExtract=!!active&&EXTRACTABLE.includes(active.status)&&active.parsed.length>0;

 return <><Heading title="إطار النتائج" description="أضف وثائق مشروعك، ثم تتبّع النتائج والمؤشرات المرتبطة بها." action={draft.indicators.length?<button className="q-btn q-primary" aria-expanded={showUpload} onClick={()=>setShowUpload(!showUpload)}><Upload size={18}/>{showUpload?'إخفاء الرفع':'رفع ملفات'}</button>:undefined}/>
 {(showUpload||!draft.indicators.length)&&<section className="q-panel q-upload-panel"><div className="q-panel-heading"><div><h2>ملفات إطار النتائج</h2><p>أضف الإطار والمسوحات والمراجع معاً، أو ابدأ بملف واحد.</p></div><span className="q-tag">حتى ٢٥ ميغابايت للملف</span></div><div className="q-upload-content"><label className="q-dropzone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy)choose(e.dataTransfer.files);}}><CloudUpload size={34}/><strong>اسحب ملفاتك هنا أو اختر من الجهاز</strong><span>Excel · CSV · Word · PDF نصي</span><input aria-label="اختيار ملفات إطار النتائج" type="file" multiple accept=".xlsx,.xlsm,.csv,.docx,.pdf" disabled={busy} onChange={e=>choose(e.target.files)}/></label>{files.map((file,index)=><div className="q-file-row" key={`${file.name}-${index}`}><FileText size={21}/><div><strong dir="auto">{file.name}</strong><small>{metric(file.size/1024)} كيلوبايت</small></div><button className="q-icon-btn" disabled={busy} aria-label={`إزالة ${file.name}`} onClick={()=>{const next=files.filter((_,i)=>i!==index);setFiles(next);setIssues(next.length?validateFiles(next):[]);}}><X size={19}/></button></div>)}{issues.length>0&&<div className="q-field-error" role="alert"><ul>{issues.map(issue=><li key={issue} dir="auto">{issue}</li>)}</ul></div>}<div className="q-upload-bottom"><p><ShieldCheck size={18}/>{connected?'ترسل الملفات فقط عند الضغط على الرفع.':'اختر الملفات الآن، واربط الخادم عندما تكون مستعداً لرفعها.'}</p><button className="q-btn q-primary" disabled={busy||!files.length} onClick={send}><Upload size={18}/>{busy?'جارٍ الرفع…':connected?'رفع وقراءة الملفات':'ربط الخادم للرفع'}</button></div></div></section>}

 {active&&<section className="q-panel q-processing-card"><div className="q-panel-heading"><div><h2>حالة الملف</h2><p dir="auto">{active.files.map(f=>f.filename).join('، ')}</p></div><Status value={active.status}/></div><div className="q-processing-content">
  {WORKING.includes(active.status)&&<p className="q-scr-working" role="status"><Loader2 size={20} className="q-scr-spin" aria-hidden="true"/>{active.status==='extracting'?'يستخرج الخادم النتائج والمؤشرات والنماذج من ملفاتك. قد يستغرق ذلك بضع دقائق، وتتحدّث الحالة هنا تلقائياً.':'يقرأ الخادم الملفات. تتحدّث الحالة هنا تلقائياً.'}</p>}
  {active.error&&<p className="q-callout q-callout-error" dir="auto">{active.error}</p>}
  {extracted&&mock&&<div className="q-callout q-scr-mock" role="note"><FlaskConical size={21} aria-hidden="true"/><div><strong>وضع الاختبار: قُرئت المسودة بالقواعد المدمجة، دون نموذج لغوي.</strong><p>راجع النتائج والمؤشرات والنماذج بعناية قبل النشر. لاستخدام نموذج لغوي اضبط في الخادم <bdi dir="ltr">LLM_MODE=real</bdi> وعنوان النموذج <bdi dir="ltr">LLM_BASE_URL</bdi>، ثم أعد الاستخراج.</p></div></div>}
  {extracted&&<div className="q-scr-summary">
   <div className="q-scr-summary-head"><h3>ملخص الاستخراج</h3></div>
   <dl className="q-scr-stats">{[['النتائج',counts.results],['المؤشرات',counts.indicators],['قواعد الحساب',counts.definitions],['الأسئلة المفتوحة',counts.open_questions]].map(([label,value])=><div key={String(label)}><dt>{label}</dt><dd>{number(value)}</dd></div>)}</dl>
   {(typeof counts.invalid_definitions==='number'&&counts.invalid_definitions>0||withoutRule!=null&&withoutRule>0)&&<ul className="q-scr-notes">{typeof counts.invalid_definitions==='number'&&counts.invalid_definitions>0&&<li>{count(counts.invalid_definitions)} من قواعد الحساب تحتاج إلى تصحيح قبل النشر.</li>}{withoutRule!=null&&withoutRule>0&&<li>{count(withoutRule)} مؤشرات بلا قاعدة حساب بعد؛ ستظهر «غير قابلة للحساب» حتى تُضاف قاعدتها.</li>}</ul>}
   <div className="q-scr-forms-split"><h4>النماذج <span>{number(counts.forms)}</span></h4><dl><div><dt>من ملفاتك</dt><dd>{number(counts.forms_from_documents)}</dd></div><div><dt>{mock?'مقترحة آلياً (وضع الاختبار)':'مقترحة من الذكاء الاصطناعي'}</dt><dd>{number(aiForms)}</dd></div></dl><a className="q-inline-link" href="#/forms">معاينة النماذج<ArrowLeft size={17}/></a></div>
   {problems.length>0&&<details className="q-technical"><summary>ملاحظات الاستخراج ({count(problems.length)})</summary><p>رسائل الخادم كما وردت. راجع العناصر المذكورة في صفحة المراجعة.</p><ul className="q-scr-details">{problems.map((problem,index)=><li key={index} dir="auto">{detailText(problem)}</li>)}</ul></details>}
  </div>}
  {active.parsed.map(file=><div className="q-parsed-file" key={file.filename}><h3 dir="auto">{file.filename}</h3><div className="q-parsed-stats">{Object.entries(file.stats).map(([key,value])=><span key={key}>{statLabels[key]||key}<strong>{count(value)}</strong></span>)}</div>{file.warnings.length>0&&<details><summary>ملاحظات القراءة ({count(file.warnings.length)})</summary><ul>{file.warnings.map((warning,index)=><li key={index} dir="auto">{warning}</li>)}</ul></details>}</div>)}
  {pollError!==null&&<div className="q-callout q-callout-error" role="alert"><p>تعذر تحديث حالة المعالجة. أعد المحاولة بزر «تحديث الحالة».</p>{pollError&&<p dir="auto">{pollError}</p>}</div>}
  <div className="q-card-actions">
   <button className="q-btn" disabled={busy} onClick={()=>update(active)}><RefreshCw size={17}/>تحديث الحالة</button>
   {canExtract&&<button className={extracted?'q-btn':'q-btn q-primary'} disabled={busy||published} onClick={()=>hasDraft?setConfirm(true):extract(active)}><GitBranch size={18}/>{active.status==='parsed'?'استخراج الإطار':'إعادة الاستخراج'}</button>}
   {extracted&&<a className="q-btn q-primary" href="#/review">فتح المراجعة<ArrowLeft size={18}/></a>}
  </div>
  {canExtract&&published&&<p className="q-field-hint">الإطار منشور، لذا لا يمكن استخراج إطار جديد: سيستبدل الاستخراج الإطار المنشور.</p>}
  <p className="q-field-hint">القراءة والاستخراج ينفذهما الخادم. لا توجد خطوات أو نتائج محاكاة في الواجهة.</p>
 </div></section>}

 {draft.results.length>0&&<section className="q-panel q-framework-tree"><div className="q-panel-heading"><div><h2>هيكل النتائج</h2><p>{count(draft.results.length)} نتائج · {count(draft.indicators.length)} مؤشرات</p></div><a href="#/review" className="q-inline-link">مراجعة التفاصيل<ArrowLeft size={17}/></a></div>{draft.results.map(result=><details className="q-result-node" key={result.id} open={!result.parent_id}><summary><span className="q-tag" dir="auto">{result.level_name}</span><strong dir="auto">{result.statement}</strong>{result.code&&<bdi>{result.code}</bdi>}</summary><div>{draft.indicators.filter(i=>i.result_id===result.id).map(i=><div className="q-framework-indicator" key={i.id}><div><strong dir="auto">{i.name}</strong><p>{kindLabels[i.kind||'']||i.kind||'نوع الحساب غير محدد'} · {i.unit||'الوحدة غير محددة'}</p></div><div><span>خط الأساس <b>{metric(i.baseline,i.unit)}</b></span><span>المستهدف <b>{metric(i.target,i.unit)}</b></span></div><Status value={i.status}/></div>)}{!draft.indicators.some(i=>i.result_id===result.id)&&<p className="q-inline-empty">لا توجد مؤشرات مرتبطة مباشرة بهذه النتيجة.</p>}</div></details>)}</section>}
 {!draft.results.length&&<div className="q-source-prompt"><FileText size={28}/><div><h3>تحتاج إلى مرجع للبدء؟</h3><p>وثائق المشروع تسرد أطر نتائج عامة منشورة. يمكنك فتح المصدر الأصلي ثم رفع ملفك عند توفر الخادم.</p></div><a href="#/sources" className="q-btn">الوثائق والمصادر<ArrowLeft size={17}/></a></div>}
 {uploads.length>1&&<details className="q-technical q-scr-history"><summary>ملفات هذه الجلسة ({count(uploads.length)})</summary>{uploads.map(row=><button className="q-upload-history" key={row.id} onClick={()=>{setActive(row);setPollError(null);}}><FileText size={17}/><span dir="auto">{row.files.map(f=>f.filename).join('، ')}</span><Status value={row.status}/></button>)}</details>}

 {confirm&&active&&<Dialog title="استبدال المسودة الحالية؟" onClose={()=>{if(!busy)setConfirm(false);}}>
  <p className="q-dialog-intro">يستبدل الاستخراج المسودة الحالية كاملة: {count(draft.results.length)} نتائج و{count(draft.indicators.length)} مؤشرات وقواعد حسابها وأسئلتها، وكل النماذج غير المنشورة، بما فيها تعديلاتك والنماذج التي أنشأتها في منشئ النماذج.</p>
  <div className="q-dialog-actions"><button className="q-btn" type="button" disabled={busy} onClick={()=>setConfirm(false)}>إلغاء</button><button className="q-btn q-primary" type="button" disabled={busy} onClick={()=>extract(active)}><GitBranch size={18}/>{busy?'جارٍ البدء…':'استخراج واستبدال المسودة'}</button></div>
 </Dialog>}
 </>;
}
