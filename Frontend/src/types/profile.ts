export interface ProfileDto {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  avatar_url: string | null;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface ProfileUpdateDto {
  full_name?: string | null;
  phone?: string | null;
}
