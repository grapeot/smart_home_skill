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

export interface DeviceStatus {
  hue: HueStatus;
  wemo: Record<string, WemoDevice>;
  rinnai: RinnaiStatus;
  garage: GarageStatus;
}
