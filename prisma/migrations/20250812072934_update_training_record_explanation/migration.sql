/*
  Warnings:

  - Added the required column `explanation` to the `TrainingRecord` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "TrainingRecord" DROP COLUMN "cons";
ALTER TABLE "TrainingRecord" DROP COLUMN "pros";

-- Add the new column, but allow it to be null temporarily
ALTER TABLE "TrainingRecord" ADD COLUMN "explanation" TEXT;

-- Update all existing rows with a default explanation
UPDATE "TrainingRecord" SET "explanation" = 'No explanation provided.' WHERE "explanation" IS NULL;

-- Now, enforce the NOT NULL constraint
ALTER TABLE "TrainingRecord" ALTER COLUMN "explanation" SET NOT NULL;
