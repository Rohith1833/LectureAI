import apiClient from "./apiClient";

export interface UploadResponseData {
  upload_id: string;
  original_filename: string;
  stored_filename: string;
  size_bytes: number;
  mime_type: string;
  uploaded_at: string;
  status: string;
}

export interface UploadResponse {
  success: boolean;
  message: string;
  data: UploadResponseData;
}

/**
 * Uploads a PDF textbook file to the FastAPI backend with progress tracking.
 */
export async function uploadTextbookFile(
  file: File,
  onProgress?: (progress: number) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post<UploadResponse>("/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );
        onProgress(percentCompleted);
      }
    },
  });

  return response.data;
}
