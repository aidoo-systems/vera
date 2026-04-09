"use client";

/**
 * License status UI surfaces.
 *
 * - <LicenseExpiredScreen /> — full-screen lockdown shown when Hub reports
 *   `enforcement_level === "hard"` (license fully expired) or when the backend
 *   returns a 402 that we classify as hard.
 * - <LicenseSoftBanner /> — persistent read-only warning shown above the app
 *   when enforcement is soft (uploads/validation/summary blocked but existing
 *   documents can still be viewed/exported).
 *
 * Both components are deliberately simple and self-contained — no external
 * state, no data-fetching. The parent (AuthProvider) decides when to render.
 */

import type { ReactNode } from "react";

type LicenseExpiredScreenProps = {
  onLogout: () => void;
  contactEmail?: string;
};

export function LicenseExpiredScreen({ onLogout, contactEmail = "support@aidoo.biz" }: LicenseExpiredScreenProps): ReactNode {
  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        padding: "2rem",
      }}
    >
      <div
        className="login-card"
        style={{
          maxWidth: "480px",
          textAlign: "center",
          padding: "2.5rem 2rem",
        }}
      >
        <div style={{ fontSize: "3rem", marginBottom: "0.5rem" }} aria-hidden="true">
          ⏰
        </div>
        <h1 style={{ fontSize: "1.5rem", marginBottom: "0.75rem" }}>License expired</h1>
        <p style={{ marginBottom: "0.75rem", lineHeight: 1.5 }}>
          Your VERA license has expired and the system is currently locked. No new
          documents can be uploaded, validated, or exported until the license is renewed.
        </p>
        <p style={{ marginBottom: "1.5rem", fontSize: "0.9rem", opacity: 0.8 }}>
          Please contact your administrator at{" "}
          <a href={`mailto:${contactEmail}`}>{contactEmail}</a> to renew.
        </p>
        <button type="button" className="btn btn-primary" onClick={onLogout} data-testid="license-logout-btn">
          Sign out
        </button>
      </div>
    </div>
  );
}

type LicenseSoftBannerProps = {
  daysRemaining?: number | null;
  contactEmail?: string;
};

export function LicenseSoftBanner({ daysRemaining, contactEmail = "support@aidoo.biz" }: LicenseSoftBannerProps): ReactNode {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="license-soft-banner"
      style={{
        background: "var(--warn-bg, #fff3cd)",
        color: "var(--warn-fg, #664d03)",
        borderBottom: "1px solid var(--warn-border, #ffe69c)",
        padding: "0.6rem 1rem",
        fontSize: "0.9rem",
        textAlign: "center",
      }}
    >
      <strong>Read-only mode</strong> — your VERA license has expired. Existing
      documents can still be viewed and exported, but new uploads and validation
      are disabled. {typeof daysRemaining === "number" && daysRemaining < 0 ? `Expired ${Math.abs(daysRemaining)} day(s) ago. ` : ""}
      Contact <a href={`mailto:${contactEmail}`}>{contactEmail}</a> to renew.
    </div>
  );
}
