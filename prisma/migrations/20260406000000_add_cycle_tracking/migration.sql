/*
  Warnings:

  - Added 3 new columns to the User table for cycle tracking (recommendation experiment tracking)

*/
-- AlterTable
ALTER TABLE "User" ADD COLUMN "totalRecommendationsGenerated" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "User" ADD COLUMN "currentCycleNumber" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "User" ADD COLUMN "isExperimentComplete" BOOLEAN NOT NULL DEFAULT false;
