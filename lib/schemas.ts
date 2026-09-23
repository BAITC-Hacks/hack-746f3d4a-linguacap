import { z } from "zod";

export const MessageRequestSchema = z.object({
  message: z
    .string({
      required_error: "Enter a message before submitting.",
      invalid_type_error: "Enter a message before submitting.",
    })
    .trim()
    .min(1, "Enter a message before submitting.")
    .max(6_000, "Keep your message under 6,000 characters."),
});

export const AnalysisSchema = z.object({
  title: z.string().trim().min(1),
  summary: z.string().trim().min(1),
  score: z.number().min(0).max(100),
  recommendations: z.array(z.string().trim().min(1)).min(1).max(6),
});

export type Analysis = z.infer<typeof AnalysisSchema>;
