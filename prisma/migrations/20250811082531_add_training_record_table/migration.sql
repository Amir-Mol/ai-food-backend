/*
  Warnings:

  - You are about to drop the column `comment` on the `Feedback` table. All the data in the column will be lost.
  - Added the required column `healthinessScore` to the `Feedback` table without a default value. This is not possible if the table is not empty.
  - Added the required column `intentToTryScore` to the `Feedback` table without a default value. This is not possible if the table is not empty.
  - Added the required column `tastinessScore` to the `Feedback` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "Feedback" DROP COLUMN "comment",
ADD COLUMN     "healthinessScore" INTEGER NOT NULL,
ADD COLUMN     "intentToTryScore" INTEGER NOT NULL,
ADD COLUMN     "tastinessScore" INTEGER NOT NULL;

-- AlterTable
ALTER TABLE "User" ADD COLUMN     "name" TEXT;

-- CreateTable
CREATE TABLE "Recipe" (
    "id" TEXT NOT NULL,
    "preferences" TEXT NOT NULL,
    "recommendation" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Recipe_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TrainingRecord" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "userProfileSnapshot" JSONB NOT NULL,
    "recommendationId" TEXT NOT NULL,
    "recommendationName" TEXT NOT NULL,
    "pros" TEXT[],
    "cons" TEXT[],
    "group" TEXT,
    "liked" BOOLEAN,
    "healthinessScore" INTEGER,
    "tastinessScore" INTEGER,
    "intentToTryScore" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "TrainingRecord_pkey" PRIMARY KEY ("id")
);
