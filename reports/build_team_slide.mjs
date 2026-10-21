/** Editable three-slide briefing from trial summary's sanitized JSON.
 * Requires @oai/artifact-tool and the Codex presentation finalizer runtime.
 * The cluster-side HTML/SVG generator itself has no third-party dependency.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';

const [input, workspaceArg] = process.argv.slice(2);
if (!input || !workspaceArg) throw Error('Usage: node build_team_slide.mjs team-summary.json OUTPUT_WORKSPACE');
const workspaceDir = path.resolve(workspaceArg);
const SKILL_DIR = process.env.TRIAL_PRESENTATION_SKILL_DIR;
const RUNTIME_PYTHON = process.env.TRIAL_RUNTIME_PYTHON;
if (!SKILL_DIR || !RUNTIME_PYTHON) throw Error('Set TRIAL_PRESENTATION_SKILL_DIR and TRIAL_RUNTIME_PYTHON to the bundled runtime');
const require = createRequire(process.env.ARTIFACT_NODE_MODULES ? path.join(process.env.ARTIFACT_NODE_MODULES,'package.json') : import.meta.url);
process.env.RUNTIME_NODE_MODULES ??= process.env.ARTIFACT_NODE_MODULES;
process.env.RUNTIME_NODE ??= process.execPath;
process.env.RUNTIME_PYTHON ??= RUNTIME_PYTHON;
const {Presentation,PresentationFile} = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const {finalizePresentation,resolvePresentationFont,applyPresentationChartFont} = await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/artifact_tool_utils.mjs')).href);
const value = JSON.parse(await fs.readFile(input,'utf8'));
const font = resolvePresentationFont();
const presentation = Presentation.create({slideSize:{width:1536,height:864}});
const slide = presentation.slides.add(); slide.background.fill = '#FFFFFF';
const ink = '#163247'; const muted = '#536673';
function addText(owner,label,left,top,width,height,fontSize=26,bold=false,color=ink) {
  const item = owner.shapes.add({geometry:'textbox',position:{left,top,width,height},fill:'none',line:{fill:'none',width:0}});
  item.text = label; item.text.style = {typeface:font,fontSize,bold,color};
  return item;
}
const text=(...args)=>addText(slide,...args);
text('Compiler hardening: results so far',56,35,1400,65,46,true);
const signed = v => (v>=0?'+':'')+v.toFixed(2)+'%';
text(value.range ? `Completed point estimates: ${signed(value.range[0])} to ${signed(value.range[1])}` : 'No complete paired results yet',56,108,1400,43,30);
text('Full = candidate hardening profile. Reference = ordinary build. Negative = faster. Positive = slower.',56,165,1400,42,24);
const layouts = [...new Set(value.conditions.map(v=>v.layout))];
const measured = value.conditions.filter(v=>v.change!==null);
const shortNames = {'FFT loop':'FFT','HDF5 collective':'HDF5 coll.','HDF5 independent':'HDF5 indep.','Integrated loop':'Integrated'};
const categories = measured.map(v=>(shortNames[v.workload]??v.workload)+' / '+v.layout.replace(' ranks per node',' ranks/node').replace('full eligible-core layout','all*')+(v.status==='partial'?' (partial)':''));
const colors = ['#167D8D','#476BB3','#B8702D','#6D7582'];
const extent = Math.max(.03,Math.ceil(Math.max(...value.conditions.map(v=>Math.abs(v.change??0)))*1.2)/100);
const chart = slide.charts.add('bar',{
  position:{left:42,top:225,width:1060,height:462},
  categories,
  series:[{name:'Observed runtime change',values:measured.map(v=>Number((v.change/100).toFixed(8))),
    points:measured.map((v,i)=>({idx:i,fill:colors[layouts.indexOf(v.layout)%colors.length]}))}],
  hasLegend:false,
  barOptions:{direction:'bar',grouping:'clustered',gapWidth:65},displayBlanksAs:'gap',
  xAxis:{tickLabelPosition:'low',textStyle:{fontSize:20},line:{fill:'#98A7B0',width:1}},
  yAxis:{min:-extent,max:extent,numberFormatCode:'0.0%',textStyle:{fontSize:21},majorGridlines:{fill:'#E6EDF1',width:1}},
  dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'+0.000%;-0.000%;0.000%',textStyle:{fontSize:19}},
  chartFill:'#FFFFFF',chartLine:{fill:'none',width:0},plotAreaFill:'#FFFFFF',plotAreaLine:{fill:'none',width:0},
});
applyPresentationChartFont(chart,{fontFamily:font});
text('Coverage',1150,238,330,42,29,true);
text(`${value.complete} complete conditions\n${value.partial} partial\n${value.not_measured} not measured`,1150,293,330,135,26);
if (value.provisional) text('Missing: 8-node I/O cases',1150,405,335,32,19);
const complete = [...new Set(value.conditions.filter(v=>v.status==='complete').map(v=>v.pairs))];
text('Sample counts',1150,450,330,43,29,true);
text(complete.length===1?`${complete[0]} pairs per case\n(${complete[0]*2} process runs)`:'Counts vary by condition',1150,503,330,90,24);
const partial = value.conditions.filter(v=>v.status==='partial');
text(partial.length===1?`Partial: ${partial[0].pairs}/${partial[0].requested} pairs`:`${partial.length} partial conditions`,1150,601,330,38,24);
text('One pair = full + reference',1150,651,330,38,23);
text(value.provisional?'Provisional screenshot transcription, 16 Oct 2026. Error bars unavailable. Original build verification pending.':
  'Original paired records. Estimates shown here; 95% paired intervals appear in the HTML/SVG summary.',56,733,1420,38,23);
text(value.provisional?'Takeaway: no consistent slowdown is apparent in completed cases. Methods and next tests follow.':
  'Assess each workload using its interval, practical impact and coverage. Test design and follow-up appear on slides 2 and 3.',56,779,1420,34,22);
text(value.provisional?'Small point estimates do not prove zero overhead. *Exact 4-/8-node core counts are not visible in the photos.':
  value.build_verification+'. Each allocation remains a separate comparison.',56,818,1420,32,22);
slide.speakerNotes.text = value.sources.join('\n')+'\n'+value.definition+'\n'+value.limitation+
  '\nThe original point estimates and pair counts come from the supplied team-summary.json, generated by trial summary. No intervals or missing cases were imputed.';
const methodSlide=presentation.slides.add(); methodSlide.background.fill='#FFFFFF';
const method=(...args)=>addText(methodSlide,...args);
method('Test design and measurement',56,35,1420,65,46,true);
method('Dense MPI phase only. Synthetic library workflows. Earlier serial/package screens are separate.\n'+
  (value.scope==='stack'?'Full and reference change the caller plus the complete trial-owned library stack.':'One ordinary caller stays fixed while the complete reference/full library stack changes.'),
  56,112,1420,80,25);
method('Workloads constructed',56,207,1420,44,30,true);
const workloadRows=[
  ['FFT loop','3D forward/inverse complex FFTs. Plans reused.'],
  ['HDF5 collective','Collective writes, flush/close and read-back.'],
  ['HDF5 independent','Independent writes, flush/close and read-back.'],
  ['Integrated loop','Repeated FFTs with periodic checkpoints.'],
].filter(([label])=>value.conditions.some(v=>v.workload===label));
const table=methodSlide.tables.add({rows:workloadRows.length,columns:2,left:56,top:265,width:1420,height:workloadRows.length*70,columnWidths:[350,1070],values:workloadRows});
table.cells.block({row:0,column:0,rowCount:workloadRows.length,columnCount:2}).assign({fill:'#FFFFFF',textStyle:{typeface:font,fontSize:27,color:ink},
  margins:{left:12,right:16,top:11,bottom:10}});
table.cells.block({row:0,column:0,rowCount:workloadRows.length,columnCount:1}).textStyle.bold=true;
table.borders.assign({fill:'#E6EDF1',width:1});
method('How the comparison works',56,585,1420,44,30,true);
method('Maximum-rank loop time excludes startup, planning and final read-back.\nBalanced process pairs keep work and rank layout fixed within each pair.\nOne rank per physical core. Slurm/Open MPI uses the saved UCX fabric policy.',56,644,1420,111,26);
method(value.provisional?'Exact sizes, runtime settings and build treatment await original-record verification.':
  'Original run manifests retain input sizes, execution settings and build identities.',56,794,1420,42,24,false,muted);
methodSlide.speakerNotes.text='Constructed protocol: production/workload.c and production/campaign.py. '+
  (value.provisional?'Source 9de3504 for the 16 October stack campaign. The old FFT caller uses FFTW_ESTIMATE and reused forward/inverse complex 3D plans. '+
  'Raw run settings and emitted protection evidence remain unverified. New deployment mode, multiple fields and FFTW_MEASURE are follow-up coverage, not completed results on slide 1. ':
  'Original run manifests identify per-case dimensions, field counts, planner mode, library identities and policy versions. ')+
  'Checkpoints use contiguous data, flush/close and a final warm read-back outside loop timing. '+value.definition;
const nextSlide=presentation.slides.add(); nextSlide.background.fill='#FFFFFF';
const next=(...args)=>addText(nextSlide,...args);
next('Time interpretation and next tests',56,35,1420,65,46,true);
next('Small point estimates warrant further checks before a deployment decision.',56,112,1420,45,28);
next('Percentages and elapsed time',56,204,650,44,30,true);
next('Change = 100 x (full/reference - 1).\nPositive: slower. Negative: faster.',56,263,650,83,26);
next('Example only: a 12-hour reference job',56,374,650,45,28,true);
next('At +1%: 7 min 12 sec longer.\nAt -1%: 7 min 12 sec shorter.',56,435,650,86,28);
next('This assumes the same workload mix and a\nsustained effect across the whole job.\nLonger jobs accumulate more seconds.\nThe percentage stays the same.',56,554,650,147,26);
next(value.loop_seconds_range?`Selected loop runs: ${value.loop_seconds_range[0].toFixed(2)} to ${value.loop_seconds_range[1].toFixed(2)} seconds.`:
  'The photos do not establish actual test duration.\nThese time examples are conditional arithmetic.',56,749,650,85,24,false,muted);
next('Follow-up coverage',800,204,680,44,30,true);
next('Build verification and deployment comparison',800,267,680,42,26,true);
next('Audit flags and raw paired records. Use one fixed\nordinary caller with each library stack at 20 nodes.',800,316,680,78,25);
next('FFT grids and sustained work',800,421,680,42,26,true);
next('Vary transform sizes and loop duration. Check\nwhether any effect persists as work increases.',800,470,680,78,25);
next('I/O patterns',800,575,680,42,26,true);
next('Vary checkpoint size, cadence and read/write mix.\nCold-cache and durable-storage cost remain open.',800,624,680,78,25);
next('MPI and repeatability',800,729,680,42,26,true);
next('Add OSU. Repeat in independent allocations.\nWhole-application impact still needs evidence.',800,778,680,70,25);
nextSlide.speakerNotes.text='Time example: 12*3600*0.01=432 seconds=7 minutes12 seconds. '+
  'Conditional arithmetic, not an observed or forecast job-time effect. If only part of a job uses the affected library, '+
  'the whole-job effect also depends on the fraction of runtime spent there and on comparable execution behavior. '+
  'The 20-node batch is an initial density screen. Sustained FFT tests and broader I/O patterns are later coverage. '+
  'Individual compiler-flag attribution remains deferred. '+value.limitation;
const stagingDir = path.join(workspaceDir,'.build'); const outputDir=path.join(workspaceDir,'output');
await fs.mkdir(stagingDir,{recursive:true}); await fs.mkdir(outputDir,{recursive:true});
const candidatePath=path.join(stagingDir,'candidate.pptx');
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const FINAL_PPTX=path.join(outputDir,'compiler-hardening-briefing-3slides.pptx');
await finalizePresentation({workspaceDir,candidatePath,finalPath:FINAL_PPTX,
  pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','14630400,8229600','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','2'],
  explicitTotalSlideCount:3,requiredNativeChartOwnerSlides:[1],requiredNativeTableOwnerSlides:[2],
  materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
  receiptPath:path.join(stagingDir,'validation.json')});
for (const [index,page] of presentation.slides.items.entries()) {
  const png=await presentation.export({slide:page,format:'png',scale:1.25});
  await fs.writeFile(path.join(outputDir,`compiler-hardening-briefing-3slides-${index+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
console.log(FINAL_PPTX);
