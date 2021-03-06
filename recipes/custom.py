# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python
import os
import shutil

from cerbero.build import recipe
from cerbero.config import Platform
from cerbero.utils import to_unixpath


class GStreamerStatic(recipe.Recipe):

    config_sh = 'sh ./autogen.sh --noconfigure && ./configure'
    configure_options = "--enable-introspection=no --disable-examples --enable-static-plugins --disable-shared --enable-static --with-package-origin='http://www.gstreamer.com' --with-package-name='GStreamer (GStreamer SDK)' "
    extra_configure_options = ''
    # Static build will always fail on make check
    make_check = None

    def prepare(self):
        self.project_name = self.name.replace('-static', '')
        self.remotes = {'upstream': 'git://anongit.freedesktop.org/gstreamer/%s'
                        % self.project_name}

        if self.config.target_platform in [Platform.WINDOWS, Platform.DARWIN]:
            self.configure_options += ' --disable-gtk-doc'
        self.configure_options += ' ' + self.extra_configure_options

        self.remotes['origin'] = ('%s/%s.git' %
                (self.config.git_root, self.project_name))

        self.tmp_destdir = os.path.join(self.build_dir, 'static-build')
        self.make_install = 'make install DESTDIR=%s' % self.tmp_destdir
        self.repo_dir = os.path.join(self.config.local_sources,
                                     self.project_name)

        # Fill the list of files with the static library and the libtool link
        # library, libgstplugin.a and libgstplugin.la
        self.plugins_categories = [x for x in dir(self) if
                x.startswith('files_plugins')]
        self.platform_plugins_categories = [x for x in dir(self) if
                x.startswith('platform_files_plugins')]
        self._files_list = []
        for name in self.plugins_categories:
            files =getattr(self, name)
            f = ['lib/gstreamer-0.10/static/%s.a' % x for x in files]
            f.extend(['lib/gstreamer-0.10/static/%s.la' % x for x in files])
            setattr(self, name, f)
            self._files_list.extend(f)
        for name in self.platform_plugins_categories:
            platform_files = getattr(self, name)
            files = platform_files.get(self.config.target_platform, [])
            f = ['lib/gstreamer-0.10/static/%s.a' % x for x in files]
            f.extend(['lib/gstreamer-0.10/static/%s.la' % x for x in files])
            platform_files[self.config.target_platform] = f
            self._files_list.extend(f)

    def configure(self):
        if not os.path.exists(self.tmp_destdir):
            os.makedirs(self.tmp_destdir)
        self.btype.configure(self)

    def post_install(self):
        if not self._files_list:
            return
        plugins_dir = os.path.dirname(os.path.join(self.config.prefix,
                                                   self._files_list[0]))
        if not os.path.exists(plugins_dir):
            os.makedirs(plugins_dir)
        # Copy all files installed in the temporary build-static directory
        # to the prefix. Static plugins will be installed in
        # lib/gstreamer-0.10/static to avoid conflicts with the libgstplugin.la
        # generated with the shared build
        for f in self._files_list:
            f_no_static = f.replace('/static/', '/')
            shutil.copyfile(os.path.join(self.tmp_destdir,
                to_unixpath(self.config.prefix)[1:], f_no_static),
                os.path.join(self.config.prefix, f))
