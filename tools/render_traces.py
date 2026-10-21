#!/usr/bin/env python3
"""Render synthetic, executable-checked examples; requires only Python 3."""
import argparse
import csv
import html
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# name: (title, naive label, component label, y limit, caption, x-axis unit)
SPECS = {
    'presence': ('Qualify jack presence before changing routing', 'Individual probe mismatch', 'Qualified presence', 1,
                 'Synthetic probe decisions: 4 per window; 2 bad windows required. Not an electrical trace.', 'Sample'),
    'pickup': ('Hold the stored value until the knob reaches it', 'Apply every knob sample', 'Apply after pickup', 100,
               'Synthetic travel in percent. Stored target: 30. A coarse move crosses it at sample 6.', 'Sample'),
    'gesture': ('A consumed modifier gesture performs one action', 'Edit plus release action', 'Consumed release suppressed', 2,
                'Synthetic cumulative action count. Press at 1; modifier edit at 3; release at 4.', 'Sample'),
    'trigger_delay': ('Keep each delayed trigger until its own deadline', 'One shared pending mask', 'Per-deadline buckets', 2,
                      'Synthetic cumulative deliveries. A at tick 0, B at tick 1, both delayed 3 ticks; not a timing measurement.', 'Tick'),
    'events': ('Count edges at the acquisition rate, drain them later', 'Level polled every third sample', 'Pending edge count', 4,
               'Synthetic cumulative events seen by the consumer. Four 2-sample pulses; the consumer reads every third sample.', 'Sample'),
    'hysteresis': ('Hold a selection on a noisy bin boundary', 'Plain truncation', 'Hysteretic selector', 3,
                   'Synthetic 4-step selector index. Readings hover within 0.03 of the 0.5 boundary, then move to 0.65. Dead band 0.2 step.', 'Sample'),
    'debounce': ('Count one press for one bouncing contact', 'Raw contact closures', 'Debounced state', 5,
                 'Synthetic cumulative presses at 1 ms samples. Bounce at 4-8 ms and 18-22 ms; 5 ms qualification is illustrative.', 'Sample'),
    'transitions': ('Finish the running fade, then fade to the newest request', 'Restart the fade on every request', 'Latest request only', 2,
                    'Synthetic cumulative completed fades. Six requests at ticks 0-10, 5-tick fades; restarting finishes nothing while they arrive.', 'Tick'),
}

def render(rows, spec):
    title, before, after, limit, caption, unit = spec
    x0, x1, y0, y1 = 68, 870, 104, 230
    def path(key):
        out = []
        for i, row in enumerate(rows):
            x = x0 + (x1 - x0) * i / (len(rows) - 1)
            y = y1 - (y1 - y0) * float(row[key]) / limit
            out.append(('M' if i == 0 else 'H') + f'{x:.2f}' + (' ' if i == 0 else ' V') + f'{y:.2f}')
        return ' '.join(out)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="920" height="302" viewBox="0 0 920 302" role="img" aria-labelledby="title desc">
<title id="title">{html.escape(title)}</title><desc id="desc">{html.escape(caption)} Orange: {html.escape(before)}. Blue: {html.escape(after)}.</desc>
<rect width="920" height="302" rx="12" fill="#f7f8fa"/>
<g font-family="system-ui, sans-serif" fill="#172334">
<text x="28" y="34" font-size="21" font-weight="650">{html.escape(title)}</text>
<path d="M28 62h24" stroke="#a84b19" stroke-width="3" stroke-dasharray="6 4"/><text x="60" y="67" font-size="14">{html.escape(before)}</text>
<path d="M450 62h24" stroke="#006d96" stroke-width="3"/><text x="482" y="67" font-size="14">{html.escape(after)}</text>
<path d="M{x0} {y0}H{x1} M{x0} {y1}H{x1}" stroke="#d5dce3" fill="none"/>
<text x="27" y="{y0+5}" font-size="13">{limit}</text><text x="35" y="{y1+5}" font-size="13">0</text>
<path d="{path('direct')}" fill="none" stroke="#a84b19" stroke-width="3" stroke-dasharray="6 4"/>
<path d="{path('qualified')}" fill="none" stroke="#006d96" stroke-width="3"/>
<text x="{x0}" y="252" font-size="12">{html.escape(unit)} 0</text><text x="815" y="252" font-size="12">{len(rows)-1}</text>
<text x="28" y="284" font-size="13">{html.escape(caption)}</text>
</g></svg>
'''

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('executable', type=Path)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    output = subprocess.check_output([str(args.executable.resolve())], text=True)
    rows = list(csv.DictReader(output.splitlines()))
    assert set(row['pattern'] for row in rows) == set(SPECS)
    for name, spec in SPECS.items():
        selected = [row for row in rows if row['pattern'] == name]
        result = render(selected, spec)
        dest = ROOT / 'docs' / 'images' / (name + '.svg')
        if args.check:
            if dest.read_text() != result:
                raise SystemExit('Stale trace: ' + str(dest.relative_to(ROOT)))
        else:
            dest.write_text(result)
    print(f'PASS: {len(SPECS)} synthetic illustrations match executable traces')
if __name__ == '__main__':
    main()
