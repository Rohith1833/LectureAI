export interface HealthData {
  status: string;
}

export interface HealthResponse {
  success: boolean;
  message: string;
  data: HealthData;
}

export interface RootResponse {
  project: string;
  version: string;
}

export interface ErrorDetail {
  field: string;
  message: string;
}

export interface ErrorResponse {
  success: boolean;
  message: string;
  errors: ErrorDetail[];
}

