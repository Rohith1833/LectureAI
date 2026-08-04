import apiClient from "./apiClient";

export interface DocumentMetadata {
  title: string | null;
  author: string | null;
  subject: string | null;
  keywords: string | null;
  creation_date: string | null;
  producer: string | null;
  page_count: number;
  pdf_version: string | null;
  language: string | null;
}

export interface DocumentData {
  id: string;
  upload_id: string;
  status: "processed" | "needs_ocr";
  extraction_version: string;
  extraction_timestamp: string;
  processing_time: number;
  metadata: DocumentMetadata | null;
  ocr_status?: string | null;
  ocr_engine?: string | null;
  ocr_version?: string | null;
  ocr_confidence?: number | null;
  ocr_language?: string | null;
  ocr_processing_time?: number | null;
}

export interface DocumentResponse {
  success: boolean;
  data: DocumentData;
}

export interface PageData {
  id: string;
  page_number: number;
  width: number;
  height: number;
}

export interface PagesResponse {
  success: boolean;
  data: PageData[];
}

export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface BlockData {
  block_id: string;
  page_number: number;
  reading_order: number;
  block_type:
    | "HEADING"
    | "PARAGRAPH"
    | "LIST"
    | "TABLE"
    | "IMAGE"
    | "EQUATION"
    | "CAPTION"
    | "HEADER"
    | "FOOTER"
    | "FOOTNOTE"
    | "UNKNOWN";
  text: string;
  bounding_box: BoundingBox;
  font_size: number | null;
  font_family: string | null;
  bold: boolean;
  italic: boolean;
  confidence: number;
  parent_block_id: string | null;
  previous_block_id: string | null;
  next_block_id: string | null;
  heading_level: number | null;
  provenance?: "NATIVE" | "OCR" | "MERGED";
}

export interface TableData {
  table_id: string;
  page_number: number;
  bounding_box: BoundingBox;
  rows_count: number;
  columns_count: number;
  data: string[][];
}

export interface ImageData {
  image_id: string;
  page_number: number;
  bounding_box: BoundingBox;
  width: number;
  height: number;
  caption: string | null;
}

export interface BlocksDataResponse {
  success: boolean;
  data: {
    blocks: BlockData[];
    tables: TableData[];
    images: ImageData[];
  };
}

export interface DocumentStatistics {
  page_count: number;
  word_count: number;
  images_count: number;
  tables_count: number;
  headings_count: number;
  paragraphs_count: number;
  lists_count: number;
}

export interface StatisticsResponse {
  success: boolean;
  data: DocumentStatistics;
}

/**
 * Fetches base document info and audit metadata by ID.
 */
export async function getDocument(id: string): Promise<DocumentResponse> {
  const response = await apiClient.get<DocumentResponse>(`/documents/${id}`);
  return response.data;
}

/**
 * Fetches page dimensions mapping list for a specific document.
 */
export async function getDocumentPages(id: string): Promise<PagesResponse> {
  const response = await apiClient.get<PagesResponse>(`/documents/${id}/pages`);
  return response.data;
}

/**
 * Fetches text blocks, tables, and registered images.
 */
export async function getDocumentBlocks(id: string): Promise<BlocksDataResponse> {
  const response = await apiClient.get<BlocksDataResponse>(`/documents/${id}/blocks`);
  return response.data;
}

/**
 * Fetches document extraction metrics and content block totals.
 */
export async function getDocumentStatistics(id: string): Promise<StatisticsResponse> {
  const response = await apiClient.get<StatisticsResponse>(`/documents/${id}/statistics`);
  return response.data;
}
