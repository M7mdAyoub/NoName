import {describe,it,expect} from 'vitest';
import {emptyDraft,emptyDashboard,validateFiles,validateFormAnswers,metric} from '../workspace/model';
import type {FormSchema} from '../workspace/types';
describe('real-data-only workspace',()=>{
 it('starts without invented projects, indicators, responses, or quotes',()=>{
  expect(emptyDraft()).toEqual({results:[],indicators:[],forms:[],definitions:[],open_questions:[]});
  expect(emptyDashboard()).toEqual({published:false,results:[],indicators:[],submissions:{}});
 });
 it('distinguishes unavailable values from an actual zero',()=>{
  expect(metric(null)).toBe('—');expect(metric(undefined)).toBe('—');expect(metric(0)).toBe('٠');expect(metric(50,'%')).toBe('٥٠٪');
 });
 it('accepts documented parser formats and rejects unsupported or oversized files',()=>{
  expect(validateFiles([{name:'نتائج.xlsx',size:1024},{name:'إطار.csv',size:200}])).toEqual([]);
  expect(validateFiles([{name:'image.png',size:100}])).toHaveLength(1);
  expect(validateFiles([{name:'large.pdf',size:25*1024*1024+1}])).toHaveLength(1);
  expect(validateFiles([])).toHaveLength(1);
 });
});
const form:FormSchema={schema_version:1,title:'استجابة فعلية',fields:[
 {id:'count',type:'integer',label:'العدد',required:true,options:[],constraints:{min:0,max:10}},
 {id:'choice',type:'select_one',label:'الفئة',required:true,options:[{value:'a',label:'أ'},{value:'b',label:'ب'}]},
 {id:'visit',type:'date',label:'التاريخ',required:false,options:[]}
]};
describe('form validation matches the repository schema',()=>{
 it('accepts zero and valid options without fabricating defaults',()=>expect(validateFormAnswers(form,{count:0,choice:'a'})).toEqual([]));
 it('reports required, numeric boundaries and unknown options',()=>{
  expect(validateFormAnswers(form,{}).map(e=>e.field)).toEqual(['count','choice']);
  expect(validateFormAnswers(form,{count:11,choice:'c'}).map(e=>e.field)).toEqual(['count','choice']);
 });
 it('rejects impossible dates and invalid number types',()=>{
  expect(validateFormAnswers(form,{count:true,choice:'a',visit:'2026-02-31'}).map(e=>e.field)).toEqual(['count','visit']);
 });
});
