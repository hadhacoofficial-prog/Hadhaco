/**
 * Backend response envelope contract.
 *
 * Every FastAPI endpoint returns `BaseSuccessResponse[T]`:
 *   { success: true, code, message, data }
 * and on failure:
 *   { success: false, code, message, data: null }
 *
 * The HTTP client unwraps `data` so callers work with `T` directly and
 * never touch the envelope.
 */
export interface ApiEnvelope<T> {
  success: boolean;
  code: string;
  message: string;
  data: T | null;
}

/** Standard paginated list shape used by list endpoints (products, orders, …). */
export interface ApiPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number;
}

/** Query primitive accepted by the client's param serializer. */
export type QueryParamValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryParamValue | QueryParamValue[]>;
