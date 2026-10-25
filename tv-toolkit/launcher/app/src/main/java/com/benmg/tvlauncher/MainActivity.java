package com.benmg.tvlauncher;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextClock;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

/** Accueil minimal : fond nature qui defile + dock d'applications favorites. */
public class MainActivity extends Activity {
    private static final long ROTATE_MS = 90_000L;
    private static final long FADE_MS = 1200L;
    private static final String PREFS = "launcher";
    private static final String KEY_FAVS = "favs";
    private static final Pattern[] DEFAULTS = {
            Pattern.compile("(^|[^a-z])atlas", Pattern.CASE_INSENSITIVE),
            Pattern.compile("(^|[^a-z])iron", Pattern.CASE_INSENSITIVE),
            Pattern.compile("smart ?tube", Pattern.CASE_INSENSITIVE),
    };

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ImageView[] layers = new ImageView[2];
    private final Bitmap[] bitmaps = new Bitmap[2];
    private int top = 0;
    private LinearLayout dock;
    private boolean visible;
    private int wpIndex = -1;
    private int fallbackIndex = 0;
    private float density;

    private final Runnable rotate = new Runnable() {
        @Override public void run() {
            showNextWallpaper();
            handler.postDelayed(this, ROTATE_MS);
        }
    };

    private int dp(int v) { return Math.round(v * density); }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        density = getResources().getDisplayMetrics().density;

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        root.setClipChildren(false);

        FrameLayout bg = new FrameLayout(this);
        for (int i = 0; i < 2; i++) {
            ImageView v = new ImageView(this);
            v.setScaleType(ImageView.ScaleType.CENTER_CROP);
            v.setAlpha(i == 0 ? 1f : 0f);
            bg.addView(v, new FrameLayout.LayoutParams(-1, -1));
            layers[i] = v;
        }
        root.addView(bg, new FrameLayout.LayoutParams(-1, -1));

        // voile sombre en bas pour la lisibilite du dock
        View scrim = new View(this);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0x00000000, 0x99000000});
        scrim.setBackground(g);
        FrameLayout.LayoutParams sp = new FrameLayout.LayoutParams(-1, dp(320), Gravity.BOTTOM);
        root.addView(scrim, sp);

        LinearLayout clockBox = new LinearLayout(this);
        clockBox.setOrientation(LinearLayout.VERTICAL);
        clockBox.setGravity(Gravity.END);
        TextClock clock = new TextClock(this);
        clock.setFormat24Hour("HH:mm");
        clock.setFormat12Hour("HH:mm");
        clock.setTextColor(Color.WHITE);
        clock.setTextSize(54);
        clock.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        clock.setShadowLayer(8, 0, 2, 0x88000000);
        TextClock date = new TextClock(this);
        date.setFormat24Hour("EEEE d MMMM");
        date.setFormat12Hour("EEEE d MMMM");
        date.setTextColor(0xDDFFFFFF);
        date.setTextSize(20);
        date.setShadowLayer(6, 0, 2, 0x88000000);
        clockBox.addView(clock);
        clockBox.addView(date);
        FrameLayout.LayoutParams cp = new FrameLayout.LayoutParams(-2, -2, Gravity.TOP | Gravity.END);
        cp.setMargins(0, dp(32), dp(56), 0);
        root.addView(clockBox, cp);

        dock = new LinearLayout(this);
        dock.setOrientation(LinearLayout.HORIZONTAL);
        dock.setGravity(Gravity.CENTER);
        dock.setClipChildren(false);
        dock.setClipToPadding(false);
        dock.setPadding(dp(24), dp(14), dp(24), dp(10));
        GradientDrawable pill = new GradientDrawable();
        pill.setColor(0x55000000);
        pill.setCornerRadius(dp(40));
        dock.setBackground(pill);
        FrameLayout.LayoutParams dp1 = new FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        dp1.setMargins(0, 0, 0, dp(48));
        root.addView(dock, dp1);

        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        visible = true;
        buildDock();
        handler.removeCallbacks(rotate);
        handler.post(rotate);
    }

    @Override
    protected void onPause() {
        super.onPause();
        visible = false;
        handler.removeCallbacks(rotate);
    }

    @Override
    protected void onStop() {
        super.onStop();
        // libere la memoire pendant qu'une autre appli tourne (TV peu dotee en RAM)
        for (int i = 0; i < 2; i++) {
            layers[i].setImageDrawable(null);
            if (bitmaps[i] != null) { bitmaps[i].recycle(); bitmaps[i] = null; }
        }
        layers[0].setAlpha(1f);
        layers[1].setAlpha(0f);
        top = 0;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        io.shutdownNow();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // appui sur Home alors qu'on est deja la : retour au premier favori
        if (dock != null && dock.getChildCount() > 0) dock.getChildAt(0).requestFocus();
    }

    @Override
    public void onBackPressed() {
        // l'accueil ne quitte jamais
    }

    // ---------------------------------------------------------------- fonds

    private List<File> wallpaperFiles() {
        List<File> out = new ArrayList<>();
        File[] dirs = {new File(getFilesDir(), "wallpapers"),
                new File(getExternalFilesDir(null), "wallpapers")};
        for (File d : dirs) {
            File[] fs = d.listFiles();
            if (fs == null) continue;
            for (File f : fs) {
                String n = f.getName().toLowerCase();
                if (n.endsWith(".jpg") || n.endsWith(".jpeg") || n.endsWith(".png") || n.endsWith(".webp")) out.add(f);
            }
        }
        Collections.sort(out, new Comparator<File>() {
            @Override public int compare(File a, File b) { return a.getName().compareTo(b.getName()); }
        });
        return out;
    }

    private void showNextWallpaper() {
        final List<File> files = wallpaperFiles();
        final File next;
        if (files.isEmpty()) {
            next = null;
        } else {
            wpIndex = (wpIndex + 1) % files.size();
            next = files.get(wpIndex);
        }
        final int fb = fallbackIndex++;
        io.execute(new Runnable() {
            @Override public void run() {
                Bitmap bmp = next != null ? decode(next) : null;
                if (bmp == null) bmp = gradient(fb);
                final Bitmap result = bmp;
                runOnUiThread(new Runnable() {
                    @Override public void run() { crossfade(result); }
                });
            }
        });
    }

    private Bitmap decode(File f) {
        try {
            BitmapFactory.Options o = new BitmapFactory.Options();
            o.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(f.getAbsolutePath(), o);
            int s = 1;
            while (o.outWidth / (s * 2) >= 1920 && o.outHeight / (s * 2) >= 1080) s *= 2;
            o = new BitmapFactory.Options();
            o.inSampleSize = s;
            try {
                return BitmapFactory.decodeFile(f.getAbsolutePath(), o);
            } catch (OutOfMemoryError e) {
                o.inSampleSize = s * 2;
                o.inPreferredConfig = Bitmap.Config.RGB_565;
                return BitmapFactory.decodeFile(f.getAbsolutePath(), o);
            }
        } catch (Throwable t) {
            return null;
        }
    }

    private Bitmap gradient(int i) {
        int[][] palettes = {
                {0xFF0B1D2A, 0xFF1F5F5B, 0xFF9CC5A1},
                {0xFF1B1B3A, 0xFF693668, 0xFFF2A65A},
                {0xFF0F2027, 0xFF2C5364, 0xFF8FB8DE},
        };
        Bitmap b = Bitmap.createBitmap(640, 360, Bitmap.Config.ARGB_8888);
        Paint p = new Paint();
        p.setShader(new LinearGradient(0, 0, 0, 360, palettes[i % palettes.length], null, Shader.TileMode.CLAMP));
        new Canvas(b).drawRect(0, 0, 640, 360, p);
        return b;
    }

    private void crossfade(Bitmap bmp) {
        if (!visible) { bmp.recycle(); return; }
        final int old = top;
        final int nu = 1 - top;
        layers[nu].setImageBitmap(bmp);
        if (bitmaps[nu] != null && bitmaps[nu] != bmp) bitmaps[nu].recycle();
        bitmaps[nu] = bmp;
        layers[nu].bringToFront();
        layers[nu].setAlpha(0f);
        layers[nu].animate().alpha(1f).setDuration(FADE_MS).withEndAction(new Runnable() {
            @Override public void run() {
                layers[old].setImageDrawable(null);
                if (bitmaps[old] != null) { bitmaps[old].recycle(); bitmaps[old] = null; }
            }
        }).start();
        top = nu;
    }

    // ----------------------------------------------------------------- dock

    private List<ResolveInfo> launchables() {
        PackageManager pm = getPackageManager();
        List<ResolveInfo> all = new ArrayList<>();
        Intent a = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER);
        Intent b = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        all.addAll(pm.queryIntentActivities(a, 0));
        for (ResolveInfo r : pm.queryIntentActivities(b, 0)) {
            boolean dup = false;
            for (ResolveInfo x : all) if (x.activityInfo.packageName.equals(r.activityInfo.packageName)) dup = true;
            if (!dup) all.add(r);
        }
        List<ResolveInfo> out = new ArrayList<>();
        for (ResolveInfo r : all) if (!r.activityInfo.packageName.equals(getPackageName())) out.add(r);
        return out;
    }

    private List<String> favourites() {
        SharedPreferences sp = getSharedPreferences(PREFS, MODE_PRIVATE);
        String raw = sp.getString(KEY_FAVS, null);
        List<String> favs = new ArrayList<>();
        if (raw == null) {
            PackageManager pm = getPackageManager();
            List<ResolveInfo> apps = launchables();
            for (Pattern p : DEFAULTS) {
                for (ResolveInfo r : apps) {
                    String label = String.valueOf(r.loadLabel(pm));
                    if ((p.matcher(label).find() || p.matcher(r.activityInfo.packageName).find())
                            && !favs.contains(r.activityInfo.packageName)) {
                        favs.add(r.activityInfo.packageName);
                        break;
                    }
                }
            }
            saveFavourites(favs);
        } else if (!raw.isEmpty()) {
            Collections.addAll(favs, raw.split(","));
        }
        return favs;
    }

    private void saveFavourites(List<String> favs) {
        StringBuilder sb = new StringBuilder();
        for (String f : favs) { if (sb.length() > 0) sb.append(','); sb.append(f); }
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_FAVS, sb.toString()).apply();
    }

    private Intent launchIntentFor(String pkg) {
        PackageManager pm = getPackageManager();
        Intent i = pm.getLeanbackLaunchIntentForPackage(pkg);
        if (i == null) i = pm.getLaunchIntentForPackage(pkg);
        return i;
    }

    private void buildDock() {
        dock.removeAllViews();
        PackageManager pm = getPackageManager();
        for (final String pkg : favourites()) {
            final Intent li = launchIntentFor(pkg);
            if (li == null) continue;
            try {
                ImageView icon = new ImageView(this);
                icon.setImageDrawable(pm.getApplicationIcon(pkg));
                CharSequence label = pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0));
                View t = tile(label, icon, new View.OnClickListener() {
                    @Override public void onClick(View v) { li.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); startActivity(li); }
                });
                t.setOnLongClickListener(new View.OnLongClickListener() {
                    @Override public boolean onLongClick(View v) {
                        List<String> favs = favourites();
                        favs.remove(pkg);
                        saveFavourites(favs);
                        Toast.makeText(MainActivity.this, "Retire du dock", Toast.LENGTH_SHORT).show();
                        buildDock();
                        return true;
                    }
                });
                dock.addView(t);
            } catch (PackageManager.NameNotFoundException ignored) { }
        }
        TextView plus = new TextView(this);
        plus.setText("+");
        plus.setTextColor(Color.WHITE);
        plus.setTextSize(44);
        plus.setGravity(Gravity.CENTER);
        dock.addView(tile("Ajouter", plus, new View.OnClickListener() {
            @Override public void onClick(View v) { pickApp(); }
        }));
        final Intent settings = new Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        ImageView gear = new ImageView(this);
        ResolveInfo ri = getPackageManager().resolveActivity(settings, 0);
        if (ri != null) gear.setImageDrawable(ri.loadIcon(getPackageManager()));
        dock.addView(tile("Reglages", gear, new View.OnClickListener() {
            @Override public void onClick(View v) { startActivity(settings); }
        }));
        if (dock.getChildCount() > 0) dock.getChildAt(0).requestFocus();
    }

    private View tile(CharSequence label, View icon, View.OnClickListener click) {
        LinearLayout t = new LinearLayout(this);
        t.setOrientation(LinearLayout.VERTICAL);
        t.setGravity(Gravity.CENTER_HORIZONTAL);
        t.setClipChildren(false);
        t.setPadding(dp(14), dp(6), dp(14), dp(2));
        t.setFocusable(true);
        t.setClickable(true);
        t.setOnClickListener(click);

        final FrameLayout box = new FrameLayout(this);
        final GradientDrawable shape = new GradientDrawable();
        shape.setColor(0x33FFFFFF);
        shape.setCornerRadius(dp(20));
        box.setBackground(shape);
        box.setPadding(dp(10), dp(10), dp(10), dp(10));
        box.addView(icon, new FrameLayout.LayoutParams(-1, -1));
        t.addView(box, new LinearLayout.LayoutParams(dp(104), dp(104)));

        final TextView name = new TextView(this);
        name.setText(label);
        name.setTextColor(Color.WHITE);
        name.setTextSize(15);
        name.setSingleLine(true);
        name.setGravity(Gravity.CENTER);
        name.setAlpha(0f);
        name.setShadowLayer(6, 0, 2, 0x99000000);
        t.addView(name, new LinearLayout.LayoutParams(dp(120), ViewGroup.LayoutParams.WRAP_CONTENT));

        final View self = t;
        t.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override public void onFocusChange(View v, boolean hasFocus) {
                float s = hasFocus ? 1.22f : 1f;
                box.animate().scaleX(s).scaleY(s).setDuration(140).start();
                name.animate().alpha(hasFocus ? 1f : 0f).setDuration(140).start();
                shape.setStroke(hasFocus ? dp(3) : 0, Color.WHITE);
                shape.setColor(hasFocus ? 0x55FFFFFF : 0x33FFFFFF);
                self.invalidate();
            }
        });
        return t;
    }

    private void pickApp() {
        final PackageManager pm = getPackageManager();
        final List<ResolveInfo> apps = launchables();
        Collections.sort(apps, new Comparator<ResolveInfo>() {
            @Override public int compare(ResolveInfo a, ResolveInfo b) {
                return String.valueOf(a.loadLabel(pm)).compareToIgnoreCase(String.valueOf(b.loadLabel(pm)));
            }
        });
        String[] labels = new String[apps.size()];
        for (int i = 0; i < labels.length; i++) labels[i] = String.valueOf(apps.get(i).loadLabel(pm));
        new AlertDialog.Builder(this)
                .setTitle("Ajouter au dock")
                .setItems(labels, new android.content.DialogInterface.OnClickListener() {
                    @Override public void onClick(android.content.DialogInterface d, int which) {
                        List<String> favs = favourites();
                        String pkg = apps.get(which).activityInfo.packageName;
                        if (!favs.contains(pkg)) favs.add(pkg);
                        saveFavourites(favs);
                        buildDock();
                    }
                })
                .show();
    }
}
