import { describe, expect, it } from 'vitest'
import { DEFAULT_MOCK_DEVICES } from '@/api/mockClient'
import type { Device } from '@/api/contract'
import { deviceAddress, emptyConfig, formFromDevice, toDeviceInput } from './deviceForm'

const mqttDevice: Device = {
  ...DEFAULT_MOCK_DEVICES[0]!,
  protocol: 'mqtt',
  config: { protocol: 'mqtt', host: 'broker', port: 1883, topic: 'halle/lichtschranke', qos: 0, tls: false, password_set: true },
}

describe('Geräte-Formular', () => {
  it('liefert leere Einstellungen mit Standardwerten je Protokoll', () => {
    expect(emptyConfig('virtual')).toEqual({ protocol: 'virtual' })
    expect(emptyConfig('mqtt')).toMatchObject({ protocol: 'mqtt', host: '', port: 1883, topic: '', qos: 0, tls: false })
    expect(emptyConfig('opcua')).toMatchObject({ protocol: 'opcua', endpoint: 'opc.tcp://', node_id: '', security_mode: 'None' })
  })

  it('zeigt als Adresse das Topic bzw. die Node-ID', () => {
    expect(deviceAddress(mqttDevice)).toBe('halle/lichtschranke')
    expect(deviceAddress({ ...mqttDevice, config: { protocol: 'opcua', endpoint: 'opc.tcp://a', node_id: 'ns=2;s=X', security_mode: 'None' } })).toBe('ns=2;s=X')
    expect(deviceAddress(DEFAULT_MOCK_DEVICES[0]!)).toBe('–')
  })

  it('übernimmt ein Gerät ins Formular, ohne Passwort', () => {
    const form = formFromDevice(mqttDevice)
    expect(form).toMatchObject({ name: 'Lichtschranke', type: 'switch', config: { topic: 'halle/lichtschranke', password: '' } })
    expect(formFromDevice(undefined)).toMatchObject({ name: '', type: 'switch', config: { protocol: 'virtual' } })
  })

  it('baut die Eingabe: leeres Passwort = unverändert (null), Zahlen aus Text', () => {
    const result = toDeviceInput({ ...formFromDevice(mqttDevice), name: '  Tor  ' })
    expect(result).toEqual({ ok: true, input: expect.objectContaining({ name: 'Tor', config: expect.objectContaining({ password: null }) }) })
    const fill = toDeviceInput({ name: 'Füllstand', type: 'number', config: { protocol: 'virtual' }, unit: 'l', min: '0', max: '' })
    expect(fill).toEqual({ ok: true, input: { name: 'Füllstand', type: 'number', config: { protocol: 'virtual' }, unit: 'l', min: 0, max: null } })
  })

  it('meldet fehlende Pflichtfelder verständlich', () => {
    const result = toDeviceInput({ name: 'X', type: 'switch', config: emptyConfig('mqtt'), unit: '', min: '', max: '' })
    expect(result.ok).toBe(false)
    expect(!result.ok && result.error).toContain('Host fehlt')
    const opc = toDeviceInput({ name: 'X', type: 'switch', config: { ...emptyConfig('opcua'), endpoint: 'http://x', node_id: 'n' }, unit: '', min: '', max: '' })
    expect(!opc.ok && opc.error).toContain('opc.tcp://')
    expect(toDeviceInput({ ...formFromDevice(undefined), name: ' ' }).ok).toBe(false)
  })
})
