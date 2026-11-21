import { DeviceInputSchema, type Device, type DeviceConfig, type DeviceInput, type DeviceProtocol, type DeviceType } from '@/api/contract'

/** Formularzustand: Zahlen als Text, damit leere Felder möglich sind. */
export type DeviceForm = {
  name: string
  type: DeviceType
  config: DeviceConfig
  unit: string
  min: string
  max: string
}

type ConfigOf<P extends DeviceProtocol> = Extract<DeviceConfig, { protocol: P }>

const EMPTY_CONFIGS: { [P in DeviceProtocol]: ConfigOf<P> } = {
  virtual: { protocol: 'virtual' },
  mqtt: { protocol: 'mqtt', host: '', port: 1883, topic: '', qos: 0, tls: false, username: '', password: '', payload_path: '' },
  opcua: { protocol: 'opcua', endpoint: 'opc.tcp://', node_id: '', security_mode: 'None', username: '', password: '' },
}

export function emptyConfig<P extends DeviceProtocol>(protocol: P): ConfigOf<P> {
  return { ...EMPTY_CONFIGS[protocol] }
}

/** Kurzangabe für die Tabelle: MQTT-Topic oder OPC-UA-Node-ID. */
export function deviceAddress(device: Device): string {
  if (device.config.protocol === 'mqtt') return device.config.topic
  if (device.config.protocol === 'opcua') return device.config.node_id
  return '–'
}

export function formFromDevice(device: Device | undefined): DeviceForm {
  if (!device) return { name: '', type: 'switch', config: emptyConfig('virtual'), unit: '', min: '', max: '' }
  const { password_set: _set, ...config } = { password_set: undefined, ...device.config }
  const withPassword = config.protocol === 'virtual' ? config : { ...config, password: '' }
  return {
    name: device.name,
    type: device.type,
    config: withPassword as DeviceConfig,
    unit: device.unit ?? '',
    min: device.min == null ? '' : String(device.min),
    max: device.max == null ? '' : String(device.max),
  }
}

const numberOrNull = (text: string) => (text.trim() === '' ? null : Number(text))
const textOrNull = (text: string | null | undefined) => (text && text.trim() !== '' ? text.trim() : null)

export function toDeviceInput(form: DeviceForm): { ok: true; input: DeviceInput } | { ok: false; error: string } {
  const config =
    form.config.protocol === 'virtual'
      ? form.config
      : {
          ...form.config,
          username: textOrNull(form.config.username),
          password: form.config.password ? form.config.password : null,
          ...(form.config.protocol === 'mqtt' ? { payload_path: textOrNull(form.config.payload_path) } : {}),
        }
  const number = form.type === 'number'
  const parsed = DeviceInputSchema.safeParse({
    name: form.name,
    type: form.type,
    config,
    ...(number ? { unit: textOrNull(form.unit), min: numberOrNull(form.min), max: numberOrNull(form.max) } : {}),
  })
  if (!parsed.success) return { ok: false, error: parsed.error.issues.map((i) => i.message).join(', ') }
  return { ok: true, input: parsed.data }
}
