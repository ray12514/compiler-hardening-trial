"""Rebuild the provisional session report from transcribed, non-sensitive evidence.

Requires reportlab. Run from any directory; no original HPC files are accessed:
    python3 /path/to/compiler-hardening-trial/reports/2026-10-16/build_report.py
All data below are screenshot transcriptions, not newly computed statistics.
"""
from pathlib import Path
import json

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.graphics.shapes import Drawing, Line, String, Circle, Rect
from reportlab.graphics import renderPDF, renderSVG

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / 'output/pdf'
OUT.mkdir(parents=True, exist_ok=True)
NAVY = HexColor('#163247')
TEAL = HexColor('#167d8d')
BLUE = HexColor('#476bb3')
ORANGE = HexColor('#b8702d')
GRAY = HexColor('#536673')
LIGHT = HexColor('#e6edf1')

production = [
    {'layout': '2 nodes / 16 ranks per node', 'pairs': 10,
     'effects_percent': [0.222, -1.077, -0.003, -2.589]},
    {'layout': '2 nodes / 92 ranks per node', 'pairs': 10,
     'effects_percent': [0.398, 0.330, 0.907, 0.022]},
    {'layout': '4 nodes / full eligible-core layout', 'pairs': 10,
     'effects_percent': [-1.288, -0.448, 1.323, -2.597]},
    {'layout': '8 nodes / full eligible-core layout', 'pairs': 4,
     'effects_percent': [-1.555, None, None, None],
     'status': 'budget_exhausted_partial'},
]
workloads = ['FFT loop', 'HDF5 collective', 'HDF5 independent', 'Integrated loop']
pilot = [
    ('FFTW / large', .377), ('FFTW / planning', -.216),
    ('FFTW / small', .311), ('FFTW / startup', 4.189),
    ('HDF5 / chunked', -.083), ('HDF5 / contiguous', -2.718),
    ('HDF5 / startup', 4.479), ('LAPACK / large', .809),
    ('LAPACK / small', 5.027), ('LAPACK / startup', 2.064),
    ('FFTW MPI / loop', -.270), ('FFTW MPI / planning', -.368),
    ('FFTW MPI / small', -.311), ('HDF5 MPI / collective', -.372),
    ('HDF5 MPI / independent', -.823), ('HDF5 MPI / small', -4.930),
]
evidence = {
    'date': '2026-10-16', 'status': 'provisional screenshot transcription',
    'production_workload_order': workloads, 'production': production,
    'latest_pilot': [{'workload': n, 'change_percent': v} for n, v in pilot],
    'provenance': {
        'latest_pilot': 'operator screenshot D12F901B',
        'two_node_16': 'operator screenshot ABAA5002',
        'two_node_92': 'operator screenshot 53A9552C (summary printed twice)',
        'four_and_eight_node': 'operator screenshot 493E372C',
    },
    'limits': ['Original manifests and pair-level results not yet reviewed.',
               'Production confidence bounds omitted from chart: final photo is clipped.',
               'No missing measurements or error bars have been imputed.'],
}
(HERE / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')


def text(x, y, value, size=10, color=NAVY, font='Helvetica'):
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawString(x, y, value)


def para(value, y, size=10.2, width=504, color=NAVY):
    p = Paragraph(value, ParagraphStyle('body', fontName='Helvetica',
                  fontSize=size, leading=size * 1.42, textColor=color))
    _, h = p.wrap(width, 700)
    p.drawOn(c, 54, y - h)
    return y - h - 12


def header(number, subtitle):
    c.setFillColor(NAVY)
    c.rect(0, 734, 612, 58, stroke=0, fill=1)
    text(54, 764, 'COMPILER HARDENING TRIAL', 11, white, 'Helvetica-Bold')
    text(54, 748, '16 October 2026  |  Provisional session report', 9, white)
    text(54, 706, subtitle, 21, NAVY, 'Helvetica-Bold')
    c.setStrokeColor(LIGHT)
    c.line(54, 44, 558, 44)
    text(54, 29, 'Screenshot-derived evidence | No private system identifiers', 8, GRAY)
    text(538, 29, f'{number} / 3', 8, GRAY)


def plot_base(width, height, left, right, bottom, top, lo, hi, ticks):
    d = Drawing(width, height)
    def xx(v):
        return left + (v-lo)/(hi-lo)*(right-left)
    for tick in ticks:
        d.add(Line(xx(tick), bottom, xx(tick), top,
                   strokeColor=LIGHT if tick else GRAY,
                   strokeWidth=.7 if tick else 1.2))
        d.add(String(xx(tick), bottom-17, f'{tick:+g}%' if tick else '0%',
                     fontName='Helvetica', fontSize=9, textAnchor='middle', fillColor=GRAY))
    return d, xx


def production_plot():
    d, xx = plot_base(504, 288, 145, 462, 45, 255, -3.2, 2, [-3, -2, -1, 0, 1, 2])
    colors = [TEAL, BLUE, ORANGE, GRAY]
    for j, name in enumerate(workloads):
        yy = 233-j*52
        d.add(String(0, yy-3, name, fontName='Helvetica', fontSize=10, fillColor=NAVY))
        for k, row in enumerate(production):
            val = row['effects_percent'][j]
            if val is None:
                continue
            y = yy+15-k*10
            d.add(Circle(xx(val), y, 3.3, strokeColor=colors[k],
                         fillColor=white if k==3 else colors[k], strokeWidth=1.3))
    d.add(String(145, 8, 'Negative: full faster     |     Positive: full slower',
                 fontName='Helvetica', fontSize=9, fillColor=GRAY))
    return d


def pilot_plot():
    d, xx = plot_base(504, 335, 156, 465, 30, 328, -6, 6, [-6, -3, 0, 3, 6])
    for i, (name, val) in enumerate(pilot):
        y = 315-i*17.8
        d.add(String(0, y-3, name, fontName='Helvetica', fontSize=8.5, fillColor=NAVY))
        d.add(Line(xx(0), y, xx(val), y, strokeWidth=2.2,
                   strokeColor=TEAL if val < 0 else ORANGE))
        d.add(Circle(xx(val), y, 2.5, fillColor=TEAL if val < 0 else ORANGE,
                     strokeColor=None))
        d.add(String(502, y-3, f'{val:+.2f}%', fontName='Helvetica',
                     fontSize=8.5, textAnchor='end', fillColor=NAVY))
    return d


pdf = OUT / 'compiler-hardening-session-report-2026-10-16.pdf'
c = canvas.Canvas(str(pdf), pagesize=(612, 792))
c.setTitle('Compiler hardening trial - provisional findings, 16 October 2026')
c.setAuthor('Ravon Venters')
c.setSubject('Screenshot-derived package pilot and dense MPI comparison; partial eight-node evidence')

header(1, 'Encouraging results; confirmation pending')
y = para('<b>No consistent performance penalty is apparent in the completed tested '
         'conditions.</b> Small differences in both directions do not establish zero '
         'overhead or a hardening speedup. Testing is paused; this report records '
         'the evidence available at the end of the session.', 682, 11)
y = para('The dense campaign compared a hardened caller and its complete trial-owned '
         'library/dependency stack with matching reference builds. Completed conditions '
         'cover 2-node sparse and dense layouts and a 4-node dense layout. The 8-node '
         'FFT condition stopped after four of ten requested pairs when its budget expired.', y)
text(54, 545, 'Dense MPI workloads: observed runtime change', 12, NAVY, 'Helvetica-Bold')
colors = [TEAL, BLUE, ORANGE, GRAY]
labels = ['2 nodes / 16 ranks per node', '2 nodes / 92 ranks per node',
          '4 nodes / full eligible-core layout', '8 nodes / FFT only, partial (4 pairs)']
for i, (label, color) in enumerate(zip(labels, colors)):
    xx = 54+(i%2)*252
    yy = 525-(i//2)*16
    c.setFillColor(white if i==3 else color)
    c.setStrokeColor(color)
    c.circle(xx+3, yy+2, 3, fill=1, stroke=1)
    text(xx+12, yy, label, 8.2, GRAY)
d = production_plot()
renderPDF.draw(d, c, 54, 203)
renderSVG.drawToFile(d, str(HERE / 'production-effects.svg'))
y = para('<b>Read this plot as point estimates, not a significance test.</b> Each completed '
         'condition has 10 pairs. Confidence bounds are omitted because the final photos '
         'do not expose all bounds reliably; no error bars have been invented. Layouts '
         'may differ in calibrated work, so these are not strong-scaling curves.', 194, 9.5)
para('Across the 12 completed dense conditions, point estimates range from about '
     '<b>-2.60% to +1.32%</b>. The incomplete 8-node FFT estimate is about <b>-1.56%</b>. '
     'No completed paired 8-node HDF5 or integrated-loop result was shown.', y, 9.5)
c.showPage()

header(2, 'Package pilot and completed coverage')
y = para('The latest all-package pilot screenshot reports complete coverage of 16 '
         'workloads, with ten pairs per workload. The chart records its displayed '
         'point estimates. Startup and small-case variation can be large relative '
         'to the measured work.', 680)
text(54, 604, 'Latest screening pilot: observed runtime change', 12, NAVY, 'Helvetica-Bold')
d = pilot_plot()
renderPDF.draw(d, c, 54, 258)
renderSVG.drawToFile(d, str(HERE / 'package-pilot-effects.svg'))
y = para('Negative means full was faster; positive means full was slower. These '
         'pilot point estimates have substantial uncertainty: for example, the latest '
         'FFTW MPI loop is <b>-0.270% [-1.541%, +0.929%]</b>, and the MPI small HDF5 '
         'case is about <b>-4.93% [-30.90%, +29.44%]</b>, using the displayed intervals. '
         'Both span zero. Earlier pilot estimates also changed between runs.', 246, 9.5)
y = para('<b>What was accomplished.</b> The operator reported full/reference package '
         'build completion; local and inter-node MPI qualification reached finalization '
         'for both arms. The package screening pilot completed, followed by denser '
         'FFT, collective/independent HDF5, and integrated-loop comparisons. The runner '
         'now includes CPU-grant discovery and WEKA reservation checks.', y, 9.5)
para('<b>Coverage is not acceptance.</b> A passing run records successful execution '
     'under the runner checks. It does not prove an overhead threshold is met, '
     'validate every user application, or measure the security benefit. Original '
     'build, binding, fabric and pair-level records still need review.', y, 9.5)
c.showPage()

header(3, 'What this means for supplied libraries')
y = para('<b>The deployment question remains useful.</b> Users can call a hardened '
         'shared library while building their application with ordinary compiler '
         'options, subject to the normal ABI/toolchain requirements. Library compiler '
         'options do not automatically apply to the application source. Checks such '
         'as fortified libc call sites depend on the calling source compilation [1, 2].', 680)
y = para('The current experiment changes both the caller and its matching stack. '
         'A small combined difference cannot isolate the library contribution: '
         'caller and library effects can reinforce or offset each other. A real '
         'application may exercise different library paths, problem sizes, data '
         'movement, and checkpoint frequencies.', y)
text(54, y-5, 'The next comparison should match that deployment', 12, NAVY, 'Helvetica-Bold')
y = para('Use <b>one fixed, ordinarily compiled caller executable</b> with the reference '
         'library/dependency stack and then the hardened stack. Verify the intended '
         'libraries on every rank; retain compatible headers and interfaces. Keep '
         'input, work, placement and runtime policy fixed within each pair. This '
         'comparison is planned and is <b>not yet implemented</b> in the production runner.', y-22)
y = para('<b>Whole-job impact depends on time spent in affected paths.</b> If a library '
         'occupied 40% of a fixed-work job and became 1% slower, the simplest '
         'unchanged-behavior estimate would be about 0.4% longer job time. This is '
         'an illustration, not a result from today. Repetition accumulates absolute '
         'seconds; the percentage does not multiply by iterations or node count. '
         'Communication and I/O can change this relationship.', y)
text(54, y-5, 'Resume next week with the existing evidence', 12, NAVY, 'Helvetica-Bold')
y = para('<b>1.</b> Preserve original result folders and inspect complete paired '
         'timings, build identities, effective flags, loaded libraries, CPU bindings '
         'and HDF5 modes. Do not discard slow points simply because they change the result.<br/>'
         '<b>2.</b> Recompute paired intervals from the raw data; keep allocations and '
         'work definitions separate. Agree on a practically meaningful overhead '
         'threshold and the precision needed to assess it.<br/>'
         '<b>3.</b> Complete the missing 8-node conditions with recorded, frozen work '
         'and repeat selected cases in an independent allocation. Then add the fixed '
         'caller comparison and one representative application. Individual-flag '
         'experiments remain deferred.', y-22, 9.5)
y = para('<b>Evidence and method.</b> Figures transcribe operator screenshots from '
         '16 October; no original HPC result archive was available for this report. '
         'The production implementation reports 100 x (mean full / mean reference - 1) '
         'over complete pairs and resamples paired process runs for a 95% percentile '
         'bootstrap interval (2,000 resamples). Ranks and loop iterations are not '
         'independent experimental replicates. The charts preserve each layout and '
         'the partial-result status; no pooled overall effect is claimed.', y, 8.6)
y = para('[1] GCC 12.5, Instrumentation Options: '
         '<link href="https://gcc.gnu.org/onlinedocs/gcc-12.5.0/gcc/Instrumentation-Options.html" color="#167d8d">official compiler documentation</link>.<br/>'
         '[2] GNU C Library, Source Fortification: '
         '<link href="https://sourceware.org/glibc/manual/latest/html_node/Source-Fortification.html" color="#167d8d">official library documentation</link>.', y, 8.3)
if y < 52:
    raise RuntimeError(f'Page 3 content extends into footer: {y}')
c.save()
print(pdf)
