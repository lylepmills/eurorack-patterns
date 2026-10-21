#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Independent Python replay of a synthetic trace emitted by the C++ adapter."""
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'examples/daisy'))
import jack_capture as j

data = subprocess.check_output([sys.argv[1], '--trace'])
info, run, rows, changes = j.parse(data, '0123456789abcdef01234567')
assert run['count'] == 6000 and sum(r['injected'] for r in rows) == 50
assert [c['patched'] for c in changes] == [False, True, False]
assert rows[4000]['patched'] and rows[4049]['patched']
assert rows[4000]['bad_windows'] == 0

def rejected(value):
    try: j.parse(value)
    except ValueError: return
    raise AssertionError('malformed capture accepted')

def changed(index, values):
    lines = data.splitlines(keepends=True)
    fields = lines[index][:-1].split(b',')
    for k, v in values.items(): fields[k] = str(v).encode()
    lines[index] = b','.join(fields) + b'\n'
    end = lines[-1][:-1].split(b',')
    end[-1] = str(j.fnv(b''.join(lines[2:-1]))).encode()
    lines[-1] = b','.join(end) + b'\n'
    return b''.join(lines)

rejected(data[:-1]); rejected(data[:-50]); rejected(data.replace(b'JEND,7,', b'JEND,8,'))
rejected(data.replace(b'JDATA,3,', b'JDATA,2,', 1))
rejected(changed(4 + 100, {1: 99}))  # duplicate sequence, corrected checksum
rejected(changed(4 + 100, {12: 1 - rows[100]['probe']}))
rejected(changed(4 + 100, {5: 50000}))  # ADC end before sample start
rejected(changed(4 + 100, {9: 32768}))  # ambiguous voltage, stale classification
rejected(changed(4 + 100, {15: 2}))  # invalid evidence without reason
rejected(changed(4 + 100, {18: 1}))  # invented qualified state
rejected(changed(4 + 4000, {14: 0}))  # missing injected invalidation
rejected(changed(2, {1: 2000000}))  # incorrect observed fault boundary
rejected(changed(-1, {3: 1}))  # aborted run
rejected(changed(-1, {4: 1}))  # completion count
try: j.identity(data.splitlines()[0], 'wrong-build')
except ValueError: pass
else: raise AssertionError('wrong firmware identity accepted')
print('PASS: independent jack replay, complete wire integrity, negative evidence/timing/state mutations')

# An operator finish has its own checksummed boundary. A short file alone is
# never evidence of successful early completion.
import json
import tempfile
from unittest.mock import Mock
short = subprocess.check_output([sys.argv[1], '--finish-trace'])
_, stopped, stopped_rows, _ = j.parse(short)
assert stopped['duration_ms'] == 300000 and stopped['acquisition_limit_us'] == 1234500
assert stopped['finish_reason'] == 'operator' and len(stopped_rows) == 2469

def rehash(lines):
    end = lines[-1][:-1].split(b',')
    end[-1] = str(j.fnv(b''.join(lines[2:-1]))).encode()
    lines[-1] = b','.join(end) + b'\n'
    return b''.join(lines)

for finish_line in (b'JFINISH,8,1234199,1234500,1\n',
                    b'JFINISH,7,1234199,1234000,1\n',
                    b'JFINISH,7,1234199,1234500,0\n',
                    b'JFINISH,7,1234199,1234500,2\n',
                    b'JFINISH,7,1234501,1234500,1\n',
                    b'JFINISH,7,300000000,300000000,1\n'):
    lines = short.splitlines(keepends=True); lines[2] = finish_line
    rejected(rehash(lines))
lines = short.splitlines(keepends=True)
del lines[-2]
lines[-1] = lines[-1].replace(b',2469,', b',2468,')
rejected(rehash(lines))  # missing final slot, even with repaired count/checksum
rejected(short.replace(b',1234500,1\n', b',1235000,1\n'))
# A deadline finish and a finish requested before an injected fault remain
# distinguishable, and still require the complete original fault evidence.
for finish_line in (b'JFINISH,7,0,3000000,0\n', b'JFINISH,7,1200000,3000000,1\n'):
    lines = data.replace(b'"protocol":1', b'"protocol":2').splitlines(keepends=True)
    lines.insert(2, finish_line)
    assert j.parse(rehash(lines))[1]['count'] == 6000

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    (out/'metadata.json').write_text(json.dumps(dict(status='incomplete', build=dict(
        kind='eurorack-patterns-daisy-jack-bench', protocol=2))))
    (out/'started.json').write_text('{"token":7}')
    port = Mock(); port.write.return_value = len(b'JF,7\n')
    request = j.FinishRequest(out/'finish-request.json', 7, port)
    request.poll(); port.write.assert_not_called()
    assert 'Finish requested' in j.request_finish(out)
    request.poll(); request.poll()
    port.write.assert_called_once_with(b'JF,7\n'); port.flush.assert_called_once()
    (out/'finish-request.json').write_text('{"token":8}')
    try: j.FinishRequest(out/'finish-request.json', 7, port).poll()
    except ValueError: pass
    else: raise AssertionError('foreign finish token accepted')
    (out/'acquisition-complete.json').write_text('{}')
    assert 'already finished' in j.request_finish(out)
    # The idle callback can submit a request while the reader waits for the
    # first download line; it must not consume or drop any protocol bytes.
    import io, time
    fake = Mock(); fake.in_waiting = 0; fake.read.side_effect = [b'', b'JEND\n']
    raw = io.BytesIO(); poll = Mock()
    assert j.LineReader(fake, raw).read_line(time.monotonic()+1, poll) == b'JEND\n'
    assert raw.getvalue() == b'JEND\n' and poll.call_count == 2
print('PASS: token-bound early finish, exact tail coverage, fault minimum, idle delivery and idempotence')
