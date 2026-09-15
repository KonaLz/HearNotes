const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root=require('path').resolve(__dirname,'..')+'/';
const source=fs.readFileSync(root+'HearNotes/ui/app.js','utf8');
const nodes={'export':{disabled:false},'export-format':{value:'json',selectedOptions:[{textContent:'JSON'}]}};
let call,notice;
const context={localStorage:{getItem:()=>null},navigator:{language:'ja'},window:{__TAURI_INTERNALS__:{invoke:async(command,args)=>{call={command,args};return {saved:true,path:'C:/test.json'};}}},result:{filename:'会議.wav'},dirty:false,currentId:'123',URL,Blob,$:id=>nodes[id],engineUrl:x=>x,fetch:async()=>({ok:true,text:async()=>'{"text":"日本語"}'}),toast:x=>notice=x};
vm.createContext(context);
vm.runInContext(fs.readFileSync(root+'HearNotes/ui/i18n.js','utf8'),context);
vm.runInContext(source.slice(source.indexOf('function tauriInvoke('),source.indexOf('// 模型下载入口')),context);
vm.runInContext(source.slice(source.indexOf('function exportFileName('),source.indexOf('window.addEventListener("beforeunload"')),context);
(async()=>{
 await nodes.export.onclick();
 assert.equal(call.command,'save_export');assert.equal(call.args.extension,'json');assert.equal(call.args.contents,'{"text":"日本語"}');assert.equal(call.args.suggestedName,'会議_文字起こし.json');assert.equal(nodes.export.disabled,false);assert(notice.includes('C:/test.json'));
 context.window.__TAURI_INTERNALS__.invoke=async()=>{throw 'Permission denied';};
 await nodes.export.onclick(); assert(notice.includes('Permission denied'));assert.equal(nodes.export.disabled,false);
 context.window.__TAURI_INTERNALS__.invoke=async()=>({saved:false,path:null});notice=null;await nodes.export.onclick();assert.equal(notice,null);
 for(const lang of ['zh','ja','en']){vm.runInContext(`displayLanguage='${lang}'`,context);const msg=vm.runInContext('systemText("实际分出的声音数量与指定人数不同，请回听确认。")',context);if(lang!=='zh')assert(!msg.includes('实际'));const flag=vm.runInContext('systemText("说话人边界或重叠不确定")',context);if(lang!=='zh')assert(!flag.includes('说话人'));}
 console.log('PASS: actual export button passes IPC arguments; save/cancel/string error; three-language warnings and flags');
})().catch(e=>{console.error(e);process.exitCode=1;});
