# SPDX-License-Identifier: MIT
# Copyright 2026 Lyle Mills
"""Finite clock/probe-path diagnostic plan; identical work in two address ranges.

Use the installed protocol-9 image. 'Low/high' refers to SDRAM addresses, not
amount of work. The reference generator is isolated from the DUT sense node.
"""


def cases(stage):
    base = dict(audio_block=16, audio_permille=0, audio_off_ms=8000,
                dsp_voices=16, dma_kib=16, dma_period_us=2000, seconds=10)
    if stage == 'receivers':
        # D4 and D5 share a threshold setting on their digital probe port.
        # CH1 reference and CH2-derived clock retain 1.2/2.0 V hysteresis.
        return [dict(base, name=f'receiver-{mv}-r{region}', dma_region=region,
                     raw_threshold_mv=mv, mode='stream')
                for mv, order in ((1650,(3,4)), (1000,(4,3)), (2300,(3,4)))
                for region in order]
    if stage in ('waveforms', 'swapped-path'):
        result = [dict(base, name=f'load-{i+1}-r{region}', dma_region=region,
                       raw_threshold_mv=1650, mode='triggered', trigger_us=3000000)
                  for i,region in enumerate((3,4,4,3))]
        if stage == 'waveforms':
            result += [dict(base, name=f'recovery-r{region}', dma_region=region,
                            raw_threshold_mv=1650, mode='triggered', trigger_us=9000000)
                       for region in (3,4)]
        return result
    raise ValueError('unknown clock waveform stage')


def scope_configuration(api, *, sample_rate=250000, raw_threshold_mv=1650,
                        clock_scope_index=1, clock_span_v=10.0):
    if sample_rate not in (250000,1000000000) or raw_threshold_mv not in (1000,1650,2300):
        raise ValueError('unsupported diagnostic scope configuration')
    if clock_scope_index not in (0,1) or clock_span_v not in (5.0,10.0):
        raise ValueError('unsupported clock channel or voltage span')
    # Measured clock excursions clipped the original 5 V span. Keep the wider
    # span with the clock when probes are swapped; reference stays at 5 V.
    return api.MsoDeviceConfiguration(
        scope_channels=[api.MsoScopeChannelConfiguration(index=i,
            analog=api.MsoScopeAnalogChannelConfiguration(center_voltage=1.65,
                voltage_range=clock_span_v if i==clock_scope_index else 5.0,
                probe_attenuation=10.0, coupling=api.Coupling.DC),
            digital=api.MsoScopeDigitalChannelConfiguration(threshold_low_voltage=1.2,
                threshold_high_voltage=2.0, minimum_pulse_width_seconds=0)) for i in (0,1)],
        analog_sample_rate=sample_rate,
        digital_probes=[api.MsoDigitalProbeConfiguration(port_index=port,
            threshold_voltage=raw_threshold_mv/1000 if port==1 else 1.65,
            channels=[api.MsoDigitalProbeChannelConfiguration(index=i,
                minimum_pulse_width_seconds=0) for i in channels])
            for port,channels in ((0,range(4)),(1,range(2)))])


def trigger_configuration(api, reference_channel):
    if reference_channel not in (0,1):
        raise ValueError('invalid reference scope channel')
    return api.CaptureConfiguration(capture_mode=api.MsoTriggerCaptureMode(
        trigger=api.MsoAnalogTriggerConfiguration(
            channel=api.ScopeChannel(index=reference_channel,type=api.ScopeChannelType.ANALOG),
            threshold_voltage=1.65,trigger_type=api.MsoAnalogTriggerEdgeType.FALLING,
            hysteresis_voltage=.2), pre_trigger_seconds=.01,post_trigger_seconds=.04))
