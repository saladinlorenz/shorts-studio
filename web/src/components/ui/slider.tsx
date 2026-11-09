import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "../../lib/utils";

export const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> & { label?: string; display?: string }
>(({ className, label, display, ...props }, ref) => (
  <div className="w-full">
    {(label || display) && (
      <div className="mb-1 flex items-center justify-between">
        <span className="field-label">{label}</span>
        {display && <span className="font-mono text-xs text-foreground/90">{display}</span>}
      </div>
    )}
    <SliderPrimitive.Root
      ref={ref}
      className={cn("relative flex w-full touch-none select-none items-center h-5", className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-secondary">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={label}
        className="block h-3.5 w-3.5 rounded-full border border-primary/70 bg-primary shadow transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
      />
    </SliderPrimitive.Root>
  </div>
));
Slider.displayName = "Slider";
