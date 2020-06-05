# Changes the light mode on doubletap, other automations can key off this mode change.
import appdaemon.plugins.hass.hassapi as hass


class LightDoubleTap(hass.Hass):

    def initialize(self):
        for light in self.args.get('lights'):
            self.listen_event(
                callback=self.double_tap_callback,
                event='zwave.node_event',
                light=light,
                entity_id='zwave.{}'.format(light)
            )

    # Set max/min brightness on double tap up/down
    def double_tap_callback(self, event, data, kwargs):
        basic_level = data.get('basic_level')
        light_basename = kwargs.get('light')
        light_friendly = self.friendly_name('light.{}'.format(light_basename))
        light_mode_entity = 'input_select.{}_mode'.format(light_basename)

        if basic_level in [255, 0]:
            light_mode = self.get_state(light_mode_entity)

            if basic_level == 255:
                self.log('{}: Double tapped up.'.format(light_friendly))
                if light_mode == 'Maximum':
                    self.select_option(light_mode_entity, 'Automatic')
                else:
                    self.select_option(light_mode_entity, 'Maximum')

            elif basic_level == 0:
                self.log('{}: Double tapped down.'.format(light_friendly))
                if light_mode == 'Minimum':
                    self.select_option(light_mode_entity, 'Automatic')
                else:
                    self.select_option(light_mode_entity, 'Minimum')
