import {describe,it,expect} from 'vitest';
import {WorkspaceApi,sameOriginBase} from '../workspace/api';
import {detailText,formsInDefinition} from '../workspace/model';

type Call={url:string;init?:RequestInit};
function recorder(status=200,body:unknown={}){const calls:Call[]=[];const transport:typeof fetch=async(input,init)=>{calls.push({url:String(input),init});return status===204?new Response(null,{status}):new Response(JSON.stringify(body),{status});};return {calls,api:new WorkspaceApi('http://127.0.0.1:8000',transport)};}

describe('backend integration contract',()=>{
 it('polls upload status without the parsed document',async()=>{
  const {calls,api}=recorder(200,{id:'u1',status:'extracting',files:[],parsed:[],error:null});
  await api.uploadStatus('u1');
  expect(calls[0].url).toBe('http://127.0.0.1:8000/upload/u1?ir=false');
 });
 it('creates, saves and deletes forms through the builder endpoints',async()=>{
  const {calls,api}=recorder(201,{id:'f',key:'site_visit',title:'Site visit',status:'draft',schema:{schema_version:1,title:'Site visit',fields:[]}});
  await api.createForm('Site visit');
  expect(calls[0].url).toBe('http://127.0.0.1:8000/draft/forms');
  expect(calls[0].init?.method).toBe('POST');
  expect(JSON.parse(String(calls[0].init?.body))).toEqual({title:'Site visit'});
  await api.saveForm('site visit',{schema_version:1,title:'T',fields:[]});
  expect(calls[1].url).toBe('http://127.0.0.1:8000/draft/forms/site%20visit');
  expect(calls[1].init?.method).toBe('PATCH');
  expect(JSON.parse(String(calls[1].init?.body))).toEqual({schema:{schema_version:1,title:'T',fields:[]}});
 });
 it('treats 204 No Content as success for deletes',async()=>{
  const {calls,api}=recorder(204);
  await expect(api.deleteForm('old')).resolves.toBe(true);
  await expect(api.deleteDefinition('ind-1')).resolves.toBe(true);
  expect(calls.map(c=>[c.init?.method,c.url])).toEqual([['DELETE','http://127.0.0.1:8000/draft/forms/old'],['DELETE','http://127.0.0.1:8000/draft/definitions/ind-1']]);
 });
 it('connects to its own server by default, only over http(s)',()=>{
  expect(sameOriginBase({protocol:'http:',origin:'http://127.0.0.1:8000'})).toBe('http://127.0.0.1:8000');
  expect(sameOriginBase({protocol:'file:',origin:'null'})).toBeNull();
 });
});

describe('server error details become readable lines',()=>{
 it('formats request validation, publish problems and plain strings',()=>{
  expect(detailText({loc:['body','data'],msg:'Field required',type:'missing'})).toBe('data: Field required');
  expect(detailText({indicator_id:'i1',errors:['a','b']},{i1:'Sales'})).toBe('المؤشر Sales: a؛ b');
  expect(detailText({form:'survey',errors:['form has no fields']})).toBe('النموذج survey: form has no fields');
  expect(detailText("'sex': required")).toBe("'sex': required");
 });
 it('finds every form a calculation rule reads',()=>{
  expect(formsInDefinition({kind:'ratio',numerator:{count:{form:'a'}},denominator:{sum:{form:'b',field:'x'}}}).sort()).toEqual(['a','b']);
  expect(formsInDefinition({kind:'count'})).toEqual([]);
 });
});

describe('default transport',()=>{
 it('calls the browser fetch without binding it to the client (no "Illegal invocation")',async()=>{
  const original=globalThis.fetch;
  // Browsers reject fetch called with any other `this` than the global object.
  globalThis.fetch=function(this:unknown){if(this!==undefined&&this!==globalThis)throw new TypeError('Illegal invocation');return Promise.resolve(new Response(JSON.stringify({results:[]}),{status:200}));} as typeof fetch;
  try{await expect(new WorkspaceApi('http://127.0.0.1:8000').request('/draft')).resolves.toEqual({results:[]});}
  finally{globalThis.fetch=original;}
 });
});
