#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Cross-build the Daisy bench and a provenance manifest; never access hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SDK_REV = 'e1f740a5a7fe38e6d6d41281bf99fe7a2bb3827b'
SUBMODULES = ['Drivers/CMSIS-DSP', 'Drivers/CMSIS_5',
              'Drivers/CMSIS-Device/ST/STM32H7xx', 'Drivers/STM32H7xx_HAL_Driver',
              'Middlewares/ST/STM32_USB_Device_Library']

def run(*args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--libdaisy', type=Path, required=True)
    p.add_argument('--gcc', type=Path, help='Directory containing arm-none-eabi-gcc')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    sdk, out = a.libdaisy.resolve(), a.out.resolve()
    compiler = (a.gcc / 'arm-none-eabi-gcc').resolve() if a.gcc else shutil.which('arm-none-eabi-gcc')
    if not compiler: p.error('ARM GNU embedded toolchain is required')
    if run('git', '-C', sdk, 'rev-parse', 'HEAD') != SDK_REV:
        p.error('libDaisy revision mismatch; see README for the tested pin')
    if run('git', '-C', sdk, 'status', '--porcelain', '--untracked-files=no'):
        p.error('libDaisy or its submodules have tracked modifications')
    modules = {}
    for name in SUBMODULES:
        expected = run('git', '-C', sdk, 'ls-tree', 'HEAD', name).split()[2]
        actual = run('git', '-C', sdk / name, 'rev-parse', 'HEAD')
        if actual != expected: p.error('SDK submodule missing or mismatched: ' + name)
        modules[name] = actual
    files = list((ROOT / 'include/eurorack_patterns').glob('*.h'))
    files += [ROOT / 'examples/shared_control.h']
    files += [HERE / name for name in ['main.cpp', 'bench.h', 'protocol.h', 'experiment.h', 'CMakeLists.txt',
                                      'build_identity.h.in', 'build.py']]
    manifest = dict(schema=1, kind='eurorack-patterns-daisy-bench', protocol=2,
                    status='cross-built only; hardware validation pending', board='seed3',
                    source_commit=run('git', '-C', ROOT, 'rev-parse', 'HEAD'),
                    source_sha256={str(f.relative_to(ROOT)): sha(f) for f in sorted(files)},
                    sdk_revision=SDK_REV, sdk_submodules=modules,
                    compiler=run(compiler, '--version').splitlines()[0],
                    flash_address='0x90040000', storage='bootloader SRAM application',
                    sample_period_us=1000, sample_cycles=810.5, adc_bits=16, oversampling=1,
                    pot_ohms=100000, debounce_ms=10, hold_ms=600,
                    gap_threshold_us=10000, max_duration_ms=30000, startup_duration_ms=20000)
    manifest['build_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()[:24]
    out.mkdir(parents=True, exist_ok=True)
    # A failed rebuild must not leave an apparently current success manifest.
    (out / 'manifest.json').unlink(missing_ok=True)
    env = dict(os.environ)
    env['PATH'] = str(Path(compiler).parent) + os.pathsep + env.get('PATH', '')
    commands = [
        ['cmake', '-S', str(HERE), '-B', str(out), '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_C_COMPILER=' + str(compiler), '-DLIBDAISY_DIR=' + str(sdk),
         '-DEP_BUILD_ID=' + manifest['build_id']],
        ['cmake', '--build', str(out), '--parallel', '8']]
    for i, command in enumerate(commands):
        with (out / f'build-{i}.log').open('w') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit((out / f'build-{i}.log').read_text()[-8000:])
    names = ['patterns_daisy.bin', 'patterns_daisy.elf', 'patterns_daisy.map']
    if not 0 < (out / names[0]).stat().st_size < 480 * 1024:
        raise SystemExit('unexpected SRAM application image size')
    manifest['artifacts_sha256'] = {n: sha(out / n) for n in names}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Built', manifest['build_id'], 'in', out, '(not flashed)')

if __name__ == '__main__':
    main()
