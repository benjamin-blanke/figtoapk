
import { put } from '@vercel/blob';
import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 15;

// Vercel Functions have a request-body limit of approximately 4.5 MB.
// Keep the maximum ZIP size below that limit.
const MAX_ZIP_SIZE = 4 * 1024 * 1024;

export async function POST(
  request: Request
): Promise<NextResponse> {
  try {
    const formData = await request.formData();
    const file = formData.get('file');

    if (!(file instanceof File)) {
      return NextResponse.json(
        {
          error:
            'No ZIP file was received. Please choose the file again.',
        },
        { status: 400 }
      );
    }

    if (!file.name.toLowerCase().endsWith('.zip')) {
      return NextResponse.json(
        { error: 'Only ZIP files are accepted.' },
        { status: 400 }
      );
    }

    if (file.size === 0) {
      return NextResponse.json(
        { error: 'The selected ZIP file is empty.' },
        { status: 400 }
      );
    }

    if (file.size > MAX_ZIP_SIZE) {
      return NextResponse.json(
        {
          error:
            'ZIP files must be 4 MB or smaller for this upload method.',
        },
        { status: 413 }
      );
    }

    // Upload the file from the server to Vercel Blob.
    const blob = await put(file.name, file, {
      access: 'public',
      addRandomSuffix: true,
      contentType: 'application/zip',
    });

    return NextResponse.json({
      url: blob.url,
    });
  } catch (error) {
    console.error('ZIP upload failed:', error);

    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? `ZIP upload failed: ${error.message}`
            : 'ZIP upload failed. Please try again.',
      },
      { status: 500 }
    );
  }
}
