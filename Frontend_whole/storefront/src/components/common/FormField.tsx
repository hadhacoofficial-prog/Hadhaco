import { useId } from "react";

export interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

/**
 * Shared text-input field used across checkout and account forms.
 * Renders a visible label (or, if only a placeholder is given but the field
 * is required, a derived label) with a required-field asterisk, plus an
 * optional inline validation error message.
 */
export function Field({
  label,
  required,
  error,
  className = "",
  id,
  placeholder,
  ...rest
}: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <label htmlFor={inputId} className={`block ${className}`}>
      {label && (
        <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
          {label}
          {required && <span className="text-destructive"> *</span>}
        </span>
      )}
      <input
        id={inputId}
        required={required}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        className={`mt-1.5 w-full bg-background border rounded-xl px-4 py-3 text-sm outline-none focus:border-foreground focus:ring-2 focus:ring-foreground/10 transition ${
          error ? "border-destructive" : "border-border"
        }`}
        {...rest}
      />
      {error && <span className="mt-1 block text-[11px] text-destructive">{error}</span>}
    </label>
  );
}

const INDIAN_MOBILE_PATTERN = /^[6-9][0-9]{9}$/;

export function isValidIndianMobile(value: string): boolean {
  return INDIAN_MOBILE_PATTERN.test(value);
}

export function stripToDigits(value: string): string {
  return value.replace(/\D/g, "").slice(0, 10);
}

interface PhoneFieldProps extends Omit<FieldProps, "type" | "onChange"> {
  value: string;
  onValueChange: (digits: string) => void;
  error?: string;
}

/** Numeric-only, 10-digit Indian mobile number input built on top of Field. */
export function PhoneField({ value, onValueChange, ...rest }: PhoneFieldProps) {
  return (
    <Field
      {...rest}
      type="tel"
      inputMode="numeric"
      maxLength={10}
      value={value}
      onChange={(e) => onValueChange(stripToDigits(e.target.value))}
    />
  );
}
