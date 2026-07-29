export interface HueStatus {
  name: string;
  is_on: boolean;
  brightness: number;
  timer_active?: boolean;
  error?: string;
}

export interface WemoDevice {
  name: string;
  is_on: boolean | null;
  host?: string;
  error?: string;
}

export interface RinnaiStatus {
  device_id?: string;
  name?: string;
  is_online: boolean;
  set_temperature?: number;
  inlet_temp?: number;
  outlet_temp?: number;
  water_flow?: number;
  operation_enabled?: boolean;
  recirculation_enabled?: boolean;
  error?: string;
}

export interface GarageStatus {
  door_count: number;
  available: boolean;
  doors?: { index: number; label: string }[];
}

export interface RingSensorStatus {
  name?: string;
  device_type?: string;
  category_id?: number;
  faulted?: boolean;
  derived_state?: string;
  tamper_status?: string;
  comm_status?: string;
  battery_level?: number;
  battery_status?: string;
  last_update?: string | number;
  last_comm_time?: string | number;
}

export interface RingLocationStatus {
  name?: string;
  has_hubs?: boolean;
  has_alarm_base_station?: boolean;
  devices: RingSensorStatus[];
}

export interface RingStatusResponse {
  schema_version?: string;
  source?: string;
  observed_at?: string;
  locations: RingLocationStatus[];
  updated_refresh_token_available?: boolean;
  configured?: boolean;
  error?: string;
}

export interface SamsungTVStatus {
  configured?: boolean;
  is_on?: boolean;
  volume?: number;
  muted?: boolean;
  error?: string;
}

export interface DeviceStatus {
  hue?: HueStatus;
  wemo?: Record<string, WemoDevice>;
  rinnai?: RinnaiStatus;
  garage?: GarageStatus;
  ring?: RingStatusResponse;
  samsung?: SamsungTVStatus;
}
