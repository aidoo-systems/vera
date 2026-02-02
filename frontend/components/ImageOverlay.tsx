import { useEffect, useRef, useState } from "react";

export type TokenBox = {
  id: string;
  text: string;
  confidence: number;
  bbox: [number, number, number, number];
  confidenceLabel: "trusted" | "medium" | "low";
  forcedReview: boolean;
  flags: string[];
};

type ImageOverlayProps = {
  imageUrl: string;
  tokens: TokenBox[];
  imageWidth: number;
  imageHeight: number;
  selectedTokenId: string | null;
  onSelect: (tokenId: string) => void;
};

export function ImageOverlay({
  imageUrl,
  tokens,
  imageWidth,
  imageHeight,
  selectedTokenId,
  onSelect,
}: ImageOverlayProps) {
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [renderedSize, setRenderedSize] = useState({ width: 1, height: 1 });

  useEffect(() => {
    const image = imageRef.current;
    if (!image) return;

    const updateSize = () => {
      const rect = image.getBoundingClientRect();
      setRenderedSize({ width: rect.width, height: rect.height });
    };

    updateSize();
    window.addEventListener("resize", updateSize);
    return () => window.removeEventListener("resize", updateSize);
  }, []);

  const safeWidth = Math.max(imageWidth, 1);
  const safeHeight = Math.max(imageHeight, 1);
  const scaleX = renderedSize.width / safeWidth;
  const scaleY = renderedSize.height / safeHeight;

  return (
    <div className="image-overlay">
      <img
        ref={imageRef}
        src={imageUrl}
        alt="Uploaded document"
      />
      {tokens.map((token) => {
        const [x, y, w, h] = token.bbox;
        const isSelected = token.id === selectedTokenId;
        const isCritical = token.confidenceLabel === "low" || token.forcedReview;
        return (
          <button
            key={token.id}
            type="button"
            onClick={() => onSelect(token.id)}
            className={`overlay-token${isSelected ? " is-selected" : ""}${isCritical ? " is-critical" : ""}`}
            style={{
              position: "absolute",
              left: x * scaleX,
              top: y * scaleY,
              width: w * scaleX,
              height: h * scaleY,
              padding: 0,
            }}
            aria-label={`Token ${token.text}`}
          />
        );
      })}
    </div>
  );
}
