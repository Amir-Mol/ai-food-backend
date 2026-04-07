/*
  Warnings:

  - Added 1 new column to the User table for feedback submission counting to fix 5th feedback detection issue

*/
-- AlterTable
ALTER TABLE "User" ADD COLUMN "feedbackSubmissionCount" INTEGER NOT NULL DEFAULT 0;
