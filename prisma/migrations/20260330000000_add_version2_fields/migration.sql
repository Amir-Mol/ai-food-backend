/*
  Warnings:

  - Added 7 new columns to the User table for Version2 feedback summarization and recommendation generation

*/
-- AlterTable
ALTER TABLE "User" ADD COLUMN "feedbackSummaryForEmbedding" TEXT;
ALTER TABLE "User" ADD COLUMN "feedbackSummaryForLLM" TEXT;
ALTER TABLE "User" ADD COLUMN "feedbackSummaryLastUpdatedAt" TIMESTAMP(3);
ALTER TABLE "User" ADD COLUMN "recommendationGenerationStatus" VARCHAR(255) NOT NULL DEFAULT 'idle';
ALTER TABLE "User" ADD COLUMN "recommendationsReadyAt" TIMESTAMP(3);
ALTER TABLE "User" ADD COLUMN "nextAllowedGenerationAt" TIMESTAMP(3);
ALTER TABLE "User" ADD COLUMN "recommendations" JSONB;
