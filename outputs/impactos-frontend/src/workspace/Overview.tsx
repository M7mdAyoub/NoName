import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Upload,Target,ClipboardList,MessageCircleQuestion,FileText,ArrowDownToLine,PlugZap,ArrowUpLeft,ChartNoAxesCombined,MessagesSquare,RefreshCw,ChevronLeft,FlaskConical} from 'lucide-react';
import {useWorkspace} from './Context';
import {Heading,EmptyState,Status,External,count,Dialog,SearchBox,OriginBadge} from './UI';
import {metric,kindLabels,trackLabels} from './model';
import {workflow,documents,sourceFile} from './repository';
import type {DashboardIndicator,DashboardSummary,Draft,FeedingForm,Qualitative,Track} from './types';
import {csvText} from '../domain/export';

/** Order of the KPI tracking statuses, as the server computes them. */
const tracks:Track[]=['achieved','in_progress','not_started','no_target','not_computable'];
type Filter=Track|'all';
type Definitions=Draft['definitions'];

/** Arabic wording for the engine's most common "not computable" reasons; anything else is shown as the server wrote it. */
const knownReasons:Record<string,string>={
 'indicator has no definition':'لا توجد قاعدة حساب منشورة لهذا المؤشر.',
 'no values to average yet':'لا توجد قيم بعد لحساب المتوسط.',
 'denominator is zero':'المقام يساوي صفراً حتى الآن، فلا يمكن حساب النسبة.',
};
function reasonText(reason:string|null|undefined):string{
 if(!reason)return '';
 if(knownReasons[reason])return knownReasons[reason];
 if(reason.startsWith('definition does not parse'))return 'قاعدة الحساب غير صالحة، فلا يمكن حساب القيمة.';
 // validate_definition reads only published forms, so a missing form usually means it is not published yet.
 if(/form '[^']+' does not exist/.test(reason))return 'قاعدة الحساب تقرأ من نموذج غير منشور أو غير موجود، فلا يمكن حساب القيمة.';
 if(reason.includes('has a non-numeric answer'))return 'إحدى الإجابات المستخدمة في الحساب ليست رقماً، فلا يمكن حساب القيمة.';
 return `تعذر حساب القيمة: ${reason}`;
}

/** A ratio is a percentage when its scale is 100 (the server's default). Other units are shown as plain numbers, as before. */
function unitOf(i:DashboardIndicator,definitions:Definitions):string|null{
 if(i.unit==='%')return '%';
 if(i.kind!=='ratio')return i.unit;
 const scale=definitions.find(d=>d.indicator_id===i.indicator_id)?.definition?.scale;
 return scale==null||scale===100?'%':i.unit;
}
/** A computed value; a milestone's 1/0 reads as done / not done yet. */
function valueText(kind:string|null,value:number|null,unit:string|null):string{
 if(kind==='milestone'&&value!=null)return value?'منجز':'لم يُنجز بعد';
 return metric(value,unit);
}
function actualText(i:DashboardIndicator,unit:string|null):string{return valueText(i.kind,i.actual,unit);}
/** Why progress_pct is null. The server needs an actual value and a target different from the start (baseline, or 0 without one). */
function noProgressText(i:DashboardIndicator):string{
 if(i.target==null)return 'لا يوجد مستهدف لمقارنة القيمة به.';
 if(i.actual==null)return 'لا تتوفر نسبة تقدم حتى تُحسب القيمة الفعلية.';
 return i.baseline==null?'المستهدف يساوي صفراً ولا يوجد خط أساس، فلا يمكن حساب نسبة التقدم.':'المستهدف يساوي خط الأساس، فلا يمكن حساب نسبة التقدم.';
}
/** Ratio components {numerator, denominator} as numbers, or null when the server sent something else. */
function ratioParts(components:Record<string,unknown>|null):{numerator:number;denominator:number}|null{
 const n=components?.numerator,d=components?.denominator;
 return typeof n==='number'&&typeof d==='number'?{numerator:n,denominator:d}:null;
}
/** A counted Arabic noun with its number agreement: [one, two, plural for 3–10, singular for 11 and above]. */
function counted(n:number,[one,two,few,many]:[string,string,string,string]):string{
 if(n===1)return one;
 if(n===2)return two;
 const rest=n%100;
 return `${count(n)} ${rest>=3&&rest<=10?few:many}`;
}
function responses(n:number):string{return n?counted(n,['استجابة واحدة','استجابتان','استجابات','استجابة']):'لا توجد استجابات';}
function answers(n:number):string{return counted(n,['إجابة واحدة','إجابتان','إجابات','إجابة']);}
function collectHref(key:string){return `#/collect?form=${encodeURIComponent(key)}`;}

function KpiTiles({summary,active,onSelect}:{summary:DashboardSummary;active:Filter;onSelect:(filter:Filter)=>void}){
 const tiles:{key:Filter;label:string;value:number}[]=[
  {key:'all',label:'كل المؤشرات',value:summary.total},
  ...tracks.filter(t=>t!=='no_target'||summary.no_target>0).map(t=>({key:t as Filter,label:trackLabels[t],value:summary[t]})),
 ];
 return <div className="q-kpi-tiles" role="group" aria-label="تصفية المؤشرات حسب حالة التتبع">
  {tiles.map(tile=><button type="button" key={tile.key} className={`q-kpi-tile q-kpi-tile-${tile.key}`} aria-pressed={active===tile.key} onClick={()=>onSelect(active===tile.key?'all':tile.key)}>
   <span className="q-kpi-tile-label"><i aria-hidden="true"/>{tile.label}</span>
   <strong>{count(tile.value)}</strong>
   {tile.key!=='all'&&summary.total>0&&<small>{metric(Math.round(tile.value/summary.total*100),'%')} من المؤشرات</small>}
  </button>)}
 </div>;
}

function FormChip({form}:{form:FeedingForm}){
 return <a className="q-kpi-chip" href={collectHref(form.key)} title={`افتح النموذج لجمع البيانات: ${form.title}`}>
  <ClipboardList size={16} aria-hidden="true"/>
  <span dir="auto">{form.title}</span>
  <span className="q-kpi-chip-count"><span aria-hidden="true">· </span>{responses(form.submissions)}</span>
 </a>;
}

function Progress({value,track}:{value:number|null;track:Track}){
 if(value==null)return <span className="q-kpi-progress q-kpi-progress-empty"><span aria-hidden="true">—</span><span className="q-sr-only">لا تتوفر نسبة تقدم</span></span>;
 const fill=Math.min(100,Math.max(0,value));
 return <span className={`q-kpi-progress q-kpi-progress-${track}`}>
  <span className="q-kpi-bar" aria-hidden="true"><i style={{inlineSize:`${fill}%`}}/></span>
  <span className="q-kpi-pct">{metric(value,'%')}</span>
 </span>;
}

function TrackStatus({indicator}:{indicator:DashboardIndicator}){
 const reason=indicator.track==='not_computable'?reasonText(indicator.reason):'';
 return <span className="q-kpi-status" title={reason||undefined}><Status value={indicator.track}/>{reason&&<span className="q-sr-only" dir="auto">{reason}</span>}</span>;
}

function IndicatorDetail({detail,unit,onClose}:{detail:DashboardIndicator;unit:string|null;onClose:()=>void}){
 const parts=detail.kind==='ratio'?ratioParts(detail.components):null;
 const rows:[string,string][]=[
  ['نوع الحساب',kindLabels[detail.kind||'']||detail.kind||'غير محدد'],
  ['الوحدة',detail.unit||'غير محددة'],
  ['خط الأساس',metric(detail.baseline,unit)],
  ['المستهدف',metric(detail.target,unit)],
  ['القيمة الفعلية',actualText(detail,unit)],
  // A value the engine could not compute carries a default of 0 records, not a real count.
  ['السجلات المحسوبة',detail.status!=='ok'&&!detail.records?'—':count(detail.records)],
  ['دورية القياس',detail.frequency||'غير محددة'],
  ['مصدر البيانات',detail.data_source||'غير محدد'],
 ];
 return <Dialog title="تفاصيل المؤشر" onClose={onClose} wide>
  <h3 className="q-detail-title" dir="auto">{detail.name}{detail.code&&<small className="q-kpi-code"><bdi>{detail.code}</bdi></small>}</h3>
  <Status value={detail.track}/>
  {detail.track==='not_computable'&&detail.reason&&<div className="q-callout" dir="auto">{reasonText(detail.reason)}</div>}
  <section className="q-kpi-detail-progress" aria-label="التقدم نحو المستهدف">
   <span>التقدم نحو المستهدف</span>
   {detail.progress_pct==null?<p className="q-kpi-muted">{noProgressText(detail)}</p>:<Progress value={detail.progress_pct} track={detail.track}/>}
   {/* Progress is measured from the baseline towards the target, which may lie above or below it. */}
   {detail.progress_pct!=null&&(detail.progress_pct>100||detail.progress_pct<0)&&<p className="q-kpi-muted">{detail.progress_pct>100?'تجاوزت القيمة الفعلية المستهدف.':'ابتعدت القيمة الفعلية عن المستهدف مقارنةً بخط الأساس.'}</p>}
  </section>
  <dl className="q-definition-grid">{rows.map(([label,value])=><div key={label}><dt>{label}</dt><dd dir="auto">{value}</dd></div>)}</dl>
  {parts&&<div className="q-kpi-ratio"><span>مكونات النسبة</span><p><strong>{metric(parts.numerator)}</strong> من <strong>{metric(parts.denominator)}</strong></p><small>البسط من أصل المقام، كما حسبهما الخادم من الاستجابات.</small></div>}
  {detail.components&&!parts&&<details className="q-technical"><summary>مكونات العملية الحسابية</summary><pre dir="ltr">{JSON.stringify(detail.components,null,2)}</pre></details>}
  <section className="q-kpi-detail-forms">
   <h3>النماذج التي تغذّي المؤشر</h3>
   {detail.forms.length?<ul>{detail.forms.map(form=><li key={form.key}>
    <FormChip form={form}/>
    <bdi className="q-kpi-key">{form.key}</bdi>
    <OriginBadge origin={form.origin}/>
   </li>)}</ul>:<p className="q-kpi-muted">لا يوجد نموذج تقرأ منه قاعدة الحساب. راجع قاعدة حساب المؤشر في صفحة المراجعة.</p>}
  </section>
  {detail.result&&<div className="q-callout"><strong dir="auto">{detail.result.level_name}{detail.result.code&&<> · <bdi>{detail.result.code}</bdi></>}</strong><p dir="auto">{detail.result.statement}</p></div>}
  {detail.breakdowns.map(b=><section className="q-breakdown" key={b.dimension}>
   <h3 dir="auto">{b.label}</h3>
   {b.values.map((value,index)=>{
    const reason=value.status==='not_computable'?reasonText(value.reason):'';
    return <div key={index}>
     <span dir="auto">{value.label||value.value||'غير محدد'}</span>
     <strong title={reason||undefined}>{valueText(detail.kind,value.actual,unit)}{value.status==='not_computable'&&<small className="q-kpi-muted"> غير قابل للحساب</small>}{reason&&<span className="q-sr-only" dir="auto">{reason}</span>}</strong>
    </div>;
   })}
  </section>)}
  {detail.track==='not_computable'&&detail.reason&&!knownReasons[detail.reason]&&<details className="q-technical"><summary>نص السبب كما أرسله الخادم</summary><pre dir="ltr">{detail.reason}</pre></details>}
 </Dialog>;
}

function QualitativeResults({analysis,formTitles}:{analysis:Qualitative;formTitles:Record<string,string>}){
 const mock=analysis.llm?.mode==='mock';
 return <>
  {mock&&<div className="q-callout q-kpi-mock" role="note"><FlaskConical size={20} aria-hidden="true"/><div><strong>وضع الاختبار</strong><p>يعمل الخادم دون نموذج لغوي، لذلك جُمعت المحاور حسب الكلمات المشتركة بين الإجابات. الأعداد والاقتباسات مأخوذة من إجابات المستجيبين الفعلية كما هي.</p></div></div>}
  {!mock&&analysis.llm?.model&&<p className="q-kpi-muted">حلّل الإجابات النموذج <bdi>{analysis.llm.model}</bdi>.</p>}
  {!analysis.fields.length&&<p className="q-inline-empty">لا توجد حقول نصية نوعية في النماذج المنشورة. علّم الحقل النصي كحقل نوعي، وغير شخصي، ثم انشر النموذج.</p>}
  {analysis.fields.map(field=><div className="q-analysis-field" key={`${field.form}-${field.field}`}>
   <h3 dir="auto">{field.label}</h3>
   <p>النموذج: {formTitles[field.form]?<span dir="auto">{formTitles[field.form]}</span>:<bdi>{field.form}</bdi>}{field.answers>0&&<> · تم تحليل {count(field.analysed)} من أصل {answers(field.answers)}.</>}</p>
   {field.error&&<p className="q-field-error">تعذر تحليل إجابات هذا السؤال: <bdi dir="auto">{field.error}</bdi></p>}
   {!field.answers&&<p className="q-kpi-muted">لا توجد إجابات نصية على هذا السؤال بعد.</p>}
   {field.analysed>0&&!field.error&&!field.themes.length&&<p className="q-kpi-muted">لم تُستخرج محاور من هذه الإجابات.</p>}
   {field.themes.map((theme,themeIndex)=><article key={`${themeIndex}-${theme.name}`}>
    <h4 dir="auto">{theme.name}</h4>
    <p dir="auto">{theme.description}</p>
    <span>{answers(theme.count)} · {metric(theme.share_pct,'%')}</span>
    {theme.quotes.map((quote,index)=><blockquote dir="auto" key={index}>{quote}</blockquote>)}
   </article>)}
   {field.themes.length>0&&field.unthemed>0&&<p className="q-kpi-muted">إجابات لم تُصنَّف ضمن أي محور: {count(field.unthemed)}.</p>}
  </div>)}
 </>;
}

export default function Overview({openConnection}:{openConnection:()=>void}){
 const {draft,dashboard,forms,base,connected,busy,refresh,run}=useWorkspace();
 const [detail,setDetail]=useState<DashboardIndicator|null>(null),[query,setQuery]=useState(''),[tab,setTab]=useState('indicators'),[track,setTrack]=useState<Filter>('all');
 const [analysis,setAnalysis]=useState<Qualitative|null>(null),[analysing,setAnalysing]=useState(false),[analysisFailed,setAnalysisFailed]=useState(false);
 // The analysis belongs to one connection: drop it when the server is disconnected or changed, and ignore a late answer from the old one.
 const session=useRef(0);
 useEffect(()=>{session.current++;setAnalysis(null);setAnalysing(false);setAnalysisFailed(false);},[base,connected]);
 const total=Object.values(dashboard.submissions).reduce((sum,n)=>sum+n,0),questions=draft.open_questions.filter(q=>!q.answer?.trim()).length;
 const summary=dashboard.summary;
 // A filter on a tile that is no longer shown (no_target dropped to zero after a refresh) falls back to all indicators.
 const filter:Filter=track==='no_target'&&!summary.no_target?'all':track;
 const needle=query.trim().toLowerCase();
 const indicators=dashboard.indicators.filter(i=>(filter==='all'||i.track===filter)&&`${i.name} ${i.code||''} ${i.forms.map(f=>`${f.title} ${f.key}`).join(' ')}`.toLowerCase().includes(needle));
 const formTitles=Object.fromEntries(forms.map(f=>[f.key,f.title]));
 function exportData(){
  const text=csvText([
   ['رمز المؤشر','اسم المؤشر','مستوى النتيجة','الوحدة','خط الأساس','المستهدف','القيمة الفعلية','نسبة التقدم','حالة التتبع','النماذج المغذية','عدد الاستجابات','السبب'],
   ...dashboard.indicators.map(i=>[i.code,i.name,i.result?.level_name,i.unit,i.baseline,i.target,i.actual,i.progress_pct,trackLabels[i.track]||i.track,i.forms.map(f=>`${f.title} (${f.key})`).join('؛ '),i.forms.map(f=>`${f.key}: ${f.submissions}`).join('؛ '),i.reason]),
  ]);
  const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const anchor=document.createElement('a');anchor.href=url;anchor.download='qiyas-indicators.csv';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function analyse(){
  const mine=session.current;
  setAnalysing(true);setAnalysisFailed(false);
  const result=await run(api=>api.qualitative());
  if(mine!==session.current)return;
  setAnalysing(false);
  // Results are shown whatever mode the server runs in; mock mode is explained, never hidden.
  if(result)setAnalysis(result);else setAnalysisFailed(true);
 }
 const stats=[
  {title:'المؤشرات',value:draft.indicators.length,icon:Target,caption:'ضمن إطار النتائج',href:'review'},
  {title:'النماذج المنشورة',value:forms.filter(f=>f.status==='published').length,icon:ClipboardList,caption:'جاهزة لجمع البيانات',href:'collect'},
  {title:'الاستجابات',value:total,icon:FileText,caption:'مسجلة في الخادم',href:'collect'},
  {title:'أسئلة المراجعة',value:questions,icon:MessageCircleQuestion,caption:'تحتاج إلى إجابة',href:'review?tab=questions'},
 ];
 return <><Heading title="نظرة عامة" description="إطارك وبياناتك ونتائجك، في مساحة واحدة." action={<a className="q-btn q-primary" href="#/framework"><Upload size={18}/>رفع إطار النتائج</a>}/>
 {!dashboard.published&&<section className="q-start-panel"><div className="q-start-copy"><span className="q-kicker">من الخطة إلى النتيجة</span><h2>ابدأ بإطار النتائج.<br/>وابقَ قريباً من الأثر.</h2><p>ارفع وثائق مشروعك، راجع المؤشرات والنماذج، ثم اجمع البيانات وتابع ما تحقق.</p><a href="#/framework" className="q-inline-link">ابدأ من هنا<ArrowLeft size={18}/></a></div><div className="q-workflow">{workflow.map((step,index)=><a href={`#/${step.key}`} key={step.title}><span className="q-step-number">{count(index+1)}</span><div><strong>{step.title}</strong><p>{step.description}</p></div><ChevronLeft size={17}/></a>)}</div></section>}
 <div className="q-stats">{stats.map(({title,value,icon:Icon,caption,href})=><a href={`#/${href}`} className="q-stat" key={title}><div><span>{title}</span><Icon size={20}/></div><strong>{connected?count(value):'—'}</strong><p>{connected?caption:'تظهر بعد تحميل بيانات المشروع'}<ArrowUpLeft size={15}/></p></a>)}</div>
 <div className="q-content-columns"><section className="q-panel q-results-panel">
  <div className="q-panel-heading"><div><h2>تتبع المؤشرات</h2><p>حالة كل مؤشر مقارنةً بمستهدفه، والنماذج التي تجمع بياناته.</p></div>{connected&&<button className="q-icon-btn" onClick={refresh} disabled={busy} aria-label="تحديث النتائج"><RefreshCw size={19}/></button>}</div>
  <div className="q-tabs" role="tablist" aria-label="نوع النتائج"><button role="tab" aria-selected={tab==='indicators'} onClick={()=>setTab('indicators')}>المؤشرات</button><button role="tab" aria-selected={tab==='qualitative'} onClick={()=>setTab('qualitative')}>التحليل النوعي</button></div>
  {tab==='indicators'?(dashboard.indicators.length?<>
   <KpiTiles summary={summary} active={filter} onSelect={setTrack}/>
   <div className="q-table-toolbar"><SearchBox value={query} onChange={setQuery} label="ابحث عن مؤشر أو نموذج"/><button className="q-btn q-compact" onClick={exportData}><ArrowDownToLine size={17}/>تصدير CSV</button></div>
   <p className="q-kpi-shown" aria-live="polite">{filter==='all'&&!needle?`المؤشرات المنشورة: ${count(dashboard.indicators.length)}`:`المؤشرات المعروضة: ${count(indicators.length)} من ${count(dashboard.indicators.length)}`}{filter!=='all'&&<> · {trackLabels[filter]}</>}</p>
   <div className="q-table-scroll"><table className="q-kpi-table"><thead><tr><th>المؤشر</th><th>يُجمع عبر</th><th>خط الأساس</th><th>المستهدف</th><th>الفعلي</th><th>التقدم</th><th>الحالة</th></tr></thead><tbody>{indicators.map(i=>{const unit=unitOf(i,draft.definitions);return <tr key={i.indicator_id}>
    <td><button className="q-table-link" onClick={()=>setDetail(i)}><span dir="auto">{i.name}</span>{i.code&&<small><bdi>{i.code}</bdi></small>}</button>{i.result&&<small className="q-kpi-level" dir="auto">{i.result.level_name}{i.result.code&&<> · <bdi>{i.result.code}</bdi></>}</small>}</td>
    <td>{i.forms.length?<div className="q-kpi-forms">{i.forms.map(form=><FormChip form={form} key={form.key}/>)}</div>:<span className="q-kpi-none">لا يوجد نموذج</span>}</td>
    <td>{metric(i.baseline,unit)}</td>
    <td>{metric(i.target,unit)}</td>
    <td className="q-value">{actualText(i,unit)}</td>
    <td><Progress value={i.progress_pct} track={i.track}/></td>
    <td><TrackStatus indicator={i}/></td>
   </tr>;})}</tbody></table></div>
   {!indicators.length&&<div className="q-inline-empty"><p>لا توجد مؤشرات تطابق البحث أو حالة التتبع المختارة.</p>{(filter!=='all'||needle)&&<button className="q-btn q-compact" onClick={()=>{setTrack('all');setQuery('');}}>عرض كل المؤشرات</button>}</div>}
  </>:<EmptyState title="لا توجد نتائج محسوبة بعد" description={connected?'انشر إطار النتائج وابدأ جمع البيانات. ستظهر القيم الفعلية وأسباب أي نقص هنا.':'عند ربط الخادم ستظهر بيانات مشروعك الفعلية هنا، دون أرقام افتراضية.'} icon={<ChartNoAxesCombined size={29}/>}><button className="q-btn" onClick={connected?()=>{window.location.hash='/review';}:openConnection}>{connected?'الانتقال إلى المراجعة':'ربط الخادم'}<ArrowLeft size={17}/></button></EmptyState>)
  :<div className="q-analysis"><p>حلّل الإجابات النصية المؤهلة، واعرض المحاور المرتبطة بمصادرها. لا تظهر أقوال أو محاور قبل تحليل بيانات فعلية.</p><button className="q-btn" disabled={!connected||busy} onClick={analyse}><MessagesSquare size={18}/>{analysing?'جارٍ التحليل…':analysis?'إعادة التحليل':'تحليل الإجابات النصية'}</button>{analysisFailed&&!analysing&&<p className="q-callout q-callout-error" role="alert">تعذر التحليل. راجع رسالة الخطأ أعلى الصفحة ثم أعد المحاولة.</p>}{analysis&&<QualitativeResults analysis={analysis} formTitles={formTitles}/>}</div>}
 </section><aside className="q-side-panels"><section className="q-panel q-next"><span className="q-round-icon"><PlugZap size={22}/></span><h2>{connected?'خطوتك التالية':'جاهز لبيانات مشروعك'}</h2><p>{connected?(questions?`لديك ${count(questions)} أسئلة تنتظر المراجعة. افتحها وراجع ارتباط النماذج بالمؤشرات.`:'أضف إطارك أو راجع المسودة الحالية. البيانات تبقى في خادمك.'): 'هذه الواجهة لا تنشئ بيانات وهمية. اربط خدمة المشروع لتبدأ الرفع والمراجعة والجمع.'}</p><button className="q-btn q-full" onClick={connected?()=>{window.location.hash='/review';}:openConnection}>{connected?'فتح المراجعة':'إعداد الاتصال'}<ArrowLeft size={17}/></button></section><section className="q-panel q-source-panel"><h2>من وثائق المشروع</h2><p>المعلومات الوظيفية مأخوذة من المستودع الحالي.</p>{documents.slice(0,2).map(doc=><External href={sourceFile(doc.path)} key={doc.path}>{doc.title}</External>)}<a href="#/sources" className="q-inline-link">كل الوثائق والمصادر<ArrowLeft size={17}/></a></section></aside></div>
 {detail&&<IndicatorDetail detail={detail} unit={unitOf(detail,draft.definitions)} onClose={()=>setDetail(null)}/>}</>;
}
