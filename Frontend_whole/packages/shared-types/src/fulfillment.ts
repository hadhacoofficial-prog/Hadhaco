export type ShippingProvider =
  | "india_post"
  | "dtdc"
  | "delhivery"
  | "blue_dart"
  | "xpressbees"
  | "shadowfax"
  | "ekart"
  | "other";

export interface FulfillmentTimelineEntry {
  id: string;
  order_id: string;
  action: string;
  actor_id: string | null;
  admin_name: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface FulfillmentTimelineResponse {
  timeline: FulfillmentTimelineEntry[];
}

export interface DispatchOrderPayload {
  shipping_provider: ShippingProvider;
  tracking_number: string;
  dispatch_date?: string;
  expected_delivery_date?: string;
  dispatch_notes?: string;
}


export const SHIPPING_PROVIDER_LABELS: Record<ShippingProvider, string> = {
  india_post: "India Post",
  dtdc: "DTDC",
  delhivery: "Delhivery",
  blue_dart: "Blue Dart",
  xpressbees: "XpressBees",
  shadowfax: "Shadowfax",
  ekart: "Ekart",
  other: "Other",
};

export const SHIPPING_PROVIDER_URLS: Record<ShippingProvider, string> = {
  india_post: "https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx",
  dtdc: "https://www.dtdc.in/tracking",
  delhivery: "https://www.delhivery.com/tracking",
  blue_dart: "https://www.bluedart.com/tracking",
  xpressbees: "https://www.xpressbees.com/shipment-tracking",
  shadowfax: "https://www.shadowfax.in/track-order",
  ekart: "https://ekartlogistics.com",
  other: "",
};
